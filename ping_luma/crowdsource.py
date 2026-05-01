from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import secrets
import time
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

log = logging.getLogger("PingLuma.crowdsource")


@dataclass(frozen=True)
class Sample:
    user_hash: bytes  # 16-byte HMAC-SHA256 prefix
    chat_ok: bool | None
    call_ok: bool | None
    ts: float


class CrowdSourceStore:
    def __init__(
            self,
            *,
            enabled: bool = True,
            country_filter: str = "IR",
            max_age_s: int = 1200,
            max_per_messenger: int = 30,
            dedup_window_s: int = 1200,
            min_samples: int = 3,
            success_threshold: float = 0.7,
            blocked_threshold: float = 0.3,
    ) -> None:
        self._enabled = enabled
        self._country = country_filter.upper()
        self._max_age = max_age_s
        self._max = max_per_messenger
        self._dedup = dedup_window_s
        self._min = min_samples
        self._success_t = success_threshold
        self._blocked_t = blocked_threshold
        self._pepper = secrets.token_bytes(32)
        self._samples: dict[str, deque[Sample]] = {}
        self._lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        return self._enabled

    async def add_sample(
            self,
            *,
            user_id: int,
            messenger_id: str,
            country: str | None,
            chat_ok: bool | None,
            call_ok: bool | None,
    ) -> bool:
        """Persist one (messenger, user) sample. Returns True if accepted."""
        if not self._enabled:
            return False
        if not country or country.upper() != self._country:
            return False
        if not isinstance(chat_ok, bool) and not isinstance(call_ok, bool):
            return False
        h = self._hash(user_id)
        now = time.time()
        async with self._lock:
            buf = self._samples.setdefault(messenger_id, deque(maxlen=self._max))
            kept: deque[Sample] = deque(maxlen=self._max)
            for s in buf:
                if (now - s.ts) >= self._max_age:
                    continue  # expire
                if s.user_hash == h and (now - s.ts) < self._dedup:
                    continue  # supersede this user's previous sample
                kept.append(s)
            kept.append(Sample(
                user_hash=h,
                chat_ok=chat_ok if isinstance(chat_ok, bool) else None,
                call_ok=call_ok if isinstance(call_ok, bool) else None,
                ts=now,
            ))
            self._samples[messenger_id] = kept
        return True

    async def ingest_payload(
            self, *, user_id: int, payload: dict,
    ) -> int:
        """Convenience: ingest a whole WebApp payload at once.

        Returns the count of accepted per-messenger samples.
        """
        if not self._enabled:
            return 0
        country = payload.get("country") if isinstance(payload, dict) else None
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return 0
        accepted = 0
        for r in results:
            if not isinstance(r, dict):
                continue
            mid = r.get("id")
            if not isinstance(mid, str):
                continue
            ok = await self.add_sample(
                user_id=user_id,
                messenger_id=mid,
                country=country if isinstance(country, str) else None,
                chat_ok=r.get("chat_ok") if isinstance(r.get("chat_ok"), bool) else None,
                call_ok=r.get("call_ok") if isinstance(r.get("call_ok"), bool) else None,
            )
            if ok:
                accepted += 1
        if accepted:
            log.info("Crowdsource: ingested %d Iranian samples for user_hash=%s",
                     accepted, self._hash(user_id).hex()[:8])
        return accepted

    async def snapshot(self) -> dict[str, dict[str, bool | None]]:
        """Aggregate fresh samples per messenger into chat_ok / call_ok verdicts."""
        if not self._enabled:
            return {}
        out: dict[str, dict[str, bool | None]] = {}
        now = time.time()
        async with self._lock:
            for mid, buf in self._samples.items():
                fresh = [s for s in buf if (now - s.ts) < self._max_age]
                signals = self._aggregate_samples(fresh)
                if signals:
                    out[mid] = signals
        return out

    def _aggregate_samples(self, samples: Iterable[Sample]) -> dict[str, bool | None]:
        signals: dict[str, bool | None] = {}
        chat_votes: list[bool] = []
        call_votes: list[bool] = []
        # Distinct-user rule: only count one most-recent vote per user_hash.
        seen: dict[bytes, Sample] = {}
        for s in samples:
            prev = seen.get(s.user_hash)
            if prev is None or s.ts > prev.ts:
                seen[s.user_hash] = s
        for s in seen.values():
            if isinstance(s.chat_ok, bool):
                chat_votes.append(s.chat_ok)
            if isinstance(s.call_ok, bool):
                call_votes.append(s.call_ok)
        chat_v = self._verdict(chat_votes)
        if chat_v is not None:
            signals["chat_ok"] = chat_v
        call_v = self._verdict(call_votes)
        if call_v is not None:
            signals["call_ok"] = call_v
        return signals

    def _verdict(self, votes: list[bool]) -> bool | None:
        if len(votes) < self._min:
            return None
        rate = sum(1 for v in votes if v) / len(votes)
        if rate >= self._success_t:
            return True
        if rate <= self._blocked_t:
            return False
        return None

    def _hash(self, user_id: int) -> bytes:
        return hmac.new(
            self._pepper, str(int(user_id)).encode(), hashlib.sha256,
        ).digest()[:16]
