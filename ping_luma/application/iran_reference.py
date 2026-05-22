"""Iran-side reference: merged signals from up to four independent sources.
Output shape (``ResultMap``)::

    {
      "bale":  {"chat_ok": True, "call_ok": True},
      "eitaa": {"chat_ok": True, "call_ok": True},
      ...
    }

A ``None`` value means "unknown" and the formatter must show a hint, not
a verdict. A missing messenger key means "no Iran-side data at all".
"""
from __future__ import annotations

import asyncio
import logging
import time
from copy import deepcopy
from typing import Optional
from urllib.parse import urlparse

import httpx

from ping_luma.domain.messengers import MESSENGERS, Messenger
from ping_luma.infrastructure.asn import AsnMap
from ping_luma.infrastructure.crowdsource import CrowdSourceStore
from ping_luma.infrastructure.ooni import OoniClient

log = logging.getLogger("PingLuma.iran_reference")

# Module-level alias is evaluated at runtime. PEP 585 (``dict[...]``) works
# on Python 3.9, but PEP 604 (``X | None``) does not — so we keep
# ``Optional`` for the inner value type only.
ResultMap = dict[str, dict[str, Optional[bool]]]


class IranReferenceClient:
    """Façade that merges ASN + OONI + Crowdsource + HTTP signals."""

    def __init__(
            self,
            *,
            http_url: str | None = None,
            http_token: str | None = None,
            http_timeout_s: float = 6.0,
            asn_map: AsnMap | None = None,
            ooni: OoniClient | None = None,
            crowdsource: CrowdSourceStore | None = None,
            ttl_s: int = 21600,
    ) -> None:
        self._http_url = http_url
        self._http_token = http_token
        self._http_timeout = http_timeout_s
        self._asn = asn_map
        self._ooni = ooni
        self._crowd = crowdsource
        self._ttl = ttl_s

        # Slow-source cache: ASN + OONI merged.
        self._passive_cache: ResultMap = {}
        # HTTP override is cached separately so it can win without contaminating
        # the passive cache.
        self._http_cache: ResultMap = {}
        self._fetched_at: float = 0.0
        self._refresh_lock = asyncio.Lock()

    # -------- public API ----------------------------------------------------

    @property
    def configured(self) -> bool:
        """At least one Iran-side signal source is configured."""
        return (
                bool(self._http_url)
                or self._asn_active
                or self._ooni_active
                or self._crowd_active
        )

    @property
    def ttl_s(self) -> int:
        return self._ttl

    @property
    def crowdsource(self) -> CrowdSourceStore | None:
        return self._crowd

    @property
    def _asn_active(self) -> bool:
        return self._asn is not None and len(self._asn) > 0

    @property
    def _ooni_active(self) -> bool:
        return self._ooni is not None and self._ooni.configured

    @property
    def _crowd_active(self) -> bool:
        return self._crowd is not None and self._crowd.configured

    async def refresh(self, *, force: bool = False) -> ResultMap:
        """Return the merged Iran-side reference.

        Slow sources (ASN/OONI/HTTP) are refreshed when their TTL expires.
        Crowdsource is always re-aggregated on every call — it's cheap
        and we want the freshest live data from Iranian users.
        """
        if not self.configured:
            return {}
        if force or not self._is_fresh():
            await self._refresh_slow_sources(force=force)
        return await self._compose_live()

    def lookup(self, messenger_id: str) -> dict[str, bool | None]:
        return self._passive_cache.get(messenger_id, {})

    # -------- internals -----------------------------------------------------

    def _is_fresh(self) -> bool:
        return bool(self._passive_cache) and (time.time() - self._fetched_at) < self._ttl

    async def _refresh_slow_sources(self, *, force: bool) -> None:
        async with self._refresh_lock:
            if not force and self._is_fresh():
                return
            self._passive_cache = await self._build_passive()
            self._http_cache = await self._build_http()
            self._fetched_at = time.time()
            n = sum(
                1 for v in self._passive_cache.values()
                if v.get("chat_ok") is not None or v.get("call_ok") is not None
            )
            n_http = sum(
                1 for v in self._http_cache.values()
                if v.get("chat_ok") is not None or v.get("call_ok") is not None
            )
            log.info(
                "Iran reference refreshed (passive=%d/%d, http=%d/%d)",
                n, len(self._passive_cache), n_http, len(self._passive_cache),
            )

    async def _compose_live(self) -> ResultMap:
        """Combine the cached passive merge with live crowd + http override."""
        merged: ResultMap = deepcopy(self._passive_cache) or {
            m.id: {"chat_ok": None, "call_ok": None} for m in MESSENGERS
        }
        if self._crowd_active and self._crowd is not None:
            try:
                crowd = await self._crowd.snapshot()
                self._merge_into(merged, crowd)
            except Exception as exc:
                log.warning("Crowdsource snapshot failed: %s", exc)
        if self._http_cache:
            self._merge_into(merged, self._http_cache)
        return merged

    async def _build_passive(self) -> ResultMap:
        """ASN baseline → OONI overlay."""
        merged: ResultMap = {m.id: {"chat_ok": None, "call_ok": None} for m in MESSENGERS}

        if self._asn_active:
            self._apply_asn(merged)

        if self._ooni_active:
            try:
                ooni_signals = await self._refresh_ooni()
                self._merge_into(merged, ooni_signals)
            except Exception as exc:
                log.warning("OONI refresh failed: %s", exc)
        return merged

    async def _build_http(self) -> ResultMap:
        if not self._http_url:
            return {}
        try:
            return await self._refresh_http()
        except Exception as exc:
            log.warning("HTTP override fetch failed: %s", exc)
            return {}

    @staticmethod
    def _merge_into(base: ResultMap, overlay: ResultMap) -> None:
        for mid, signals in overlay.items():
            target = base.setdefault(mid, {"chat_ok": None, "call_ok": None})
            for k, v in signals.items():
                if v is not None:
                    target[k] = v

    # -------- source: ASN ---------------------------------------------------

    def _apply_asn(self, merged: ResultMap) -> None:
        assert self._asn is not None
        for m in MESSENGERS:
            if not m.turn_host:
                continue
            cls = self._asn.classify(m.turn_host)
            if cls == "iran_only_structural":
                merged[m.id]["call_ok"] = True

    # -------- source: OONI --------------------------------------------------

    async def _refresh_ooni(self) -> ResultMap:
        """Use OONI for chat-side cross-check only.

        OONI's web_connectivity tests don't exercise WebRTC, so we
        deliberately don't infer call_ok from them.
        """
        assert self._ooni is not None
        out: ResultMap = {}
        tasks: list[tuple[Messenger, asyncio.Task]] = []
        for m in MESSENGERS:
            host = _extract_host(m.probe_urls[0]) if m.probe_urls else None
            if not host:
                continue
            tasks.append((m, asyncio.create_task(self._ooni.is_reachable_from_iran(host))))
        for m, task in tasks:
            try:
                verdict = await task
            except Exception as exc:
                log.debug("OONI lookup for %s failed: %s", m.id, exc)
                verdict = None
            if verdict is not None:
                out.setdefault(m.id, {})["chat_ok"] = verdict
        return out

    # -------- source: HTTP override -----------------------------------------

    async def _refresh_http(self) -> ResultMap:
        assert self._http_url is not None  # gated by caller
        headers = (
            {"Authorization": f"Bearer {self._http_token}"} if self._http_token else {}
        )
        async with httpx.AsyncClient(timeout=self._http_timeout) as client:
            resp = await client.get(self._http_url, headers=headers)
            resp.raise_for_status()
            payload = resp.json()
        results = payload.get("results") or {}
        return {
            mid: {
                "chat_ok": _coerce_bool(v.get("chat_ok")),
                "call_ok": _coerce_bool(v.get("call_ok")),
            }
            for mid, v in results.items()
            if isinstance(v, dict)
        }


def _extract_host(url: str) -> str | None:
    try:
        return urlparse(url).hostname
    except Exception:
        return None


def _coerce_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None
