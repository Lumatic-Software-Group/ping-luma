from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger("PingLuma.ooni")


class OoniClient:
    BASE_URL = "https://api.ooni.io/api/v1"

    def __init__(
            self,
            *,
            enabled: bool = True,
            lookback_days: int = 7,
            ttl_s: int = 86400,
            http_timeout_s: float = 15.0,
            success_threshold: float = 0.7,
            confirmed_blocked_threshold: float = 0.5,
            min_measurements: int = 3,
    ) -> None:
        self._enabled = enabled
        self._lookback = lookback_days
        self._ttl = ttl_s
        self._http_timeout = http_timeout_s
        self._success_t = success_threshold
        self._blocked_t = confirmed_blocked_threshold
        self._min = min_measurements
        self._cache: dict[str, tuple[float, bool | None]] = {}
        self._lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        return self._enabled

    async def is_reachable_from_iran(self, host: str) -> bool | None:
        """Verdict from cached OONI aggregation.

        Returns:
            * ``True``  if Iranian probes mostly see the host as reachable.
            * ``False`` if Iranian probes confirm censorship.
            * ``None``  if there's not enough data or OONI is unreachable.
        """
        if not self._enabled or not host:
            return None
        cached = self._cache.get(host)
        if cached and (time.time() - cached[0]) < self._ttl:
            return cached[1]
        async with self._lock:
            cached = self._cache.get(host)
            if cached and (time.time() - cached[0]) < self._ttl:
                return cached[1]
            verdict = await self._query(host)
            self._cache[host] = (time.time(), verdict)
            return verdict

    async def _query(self, host: str) -> bool | None:
        since = (
                datetime.now(timezone.utc) - timedelta(days=self._lookback)
        ).strftime("%Y-%m-%d")
        params = {
            "probe_cc": "IR",
            "domain": host,
            "test_name": "web_connectivity",
            "since": since,
        }
        try:
            async with httpx.AsyncClient(timeout=self._http_timeout) as client:
                resp = await client.get(f"{self.BASE_URL}/aggregation", params=params)
                resp.raise_for_status()
                payload = resp.json()
        except Exception as exc:
            log.debug("OONI aggregation for %s failed: %s", host, exc)
            return None

        row = _first_row(payload)
        if row is None:
            return None

        total = _as_int(row.get("measurement_count"))
        if total < self._min:
            return None
        ok = _as_int(row.get("ok_count"))
        confirmed = _as_int(row.get("confirmed_count"))

        confirmed_rate = confirmed / total
        if confirmed_rate >= self._blocked_t:
            return False

        ok_rate = ok / total
        if ok_rate >= self._success_t:
            return True
        return None


def _first_row(payload: dict) -> dict | None:
    """OONI returns ``result`` as either a single object or a list of
    one-row aggregations depending on the request shape."""
    result = payload.get("result")
    if isinstance(result, list):
        return result[0] if result else None
    if isinstance(result, dict):
        return result
    return None


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0
