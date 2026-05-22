from __future__ import annotations

from dataclasses import dataclass, field

from ping_luma.domain.messengers import Messenger


@dataclass
class UrlResult:
    url: str
    reachable: bool
    latency_ms: float | None = None
    status_code: int | None = None
    ssl_valid: bool = False
    error: str | None = None


@dataclass
class DnsResult:
    host: str
    resolved: bool
    ip: str | None = None
    latency_ms: float | None = None


@dataclass
class StunResult:
    host: str
    port: int
    reachable: bool
    latency_ms: float | None = None
    error: str | None = None


@dataclass
class TurnResult:
    host: str
    port: int
    reachable: bool
    latency_ms: float | None = None
    error: str | None = None


@dataclass
class MessengerResult:
    messenger: Messenger
    chat_score: int
    chat_verdict: str
    best_latency_ms: float | None = None
    url_results: list[UrlResult] = field(default_factory=list)
    dns_results: list[DnsResult] = field(default_factory=list)
    call_score: int = 0
    call_verdict: str = "UNKNOWN"
    stun_results: list[StunResult] = field(default_factory=list)
    turn_result: TurnResult | None = None

    @property
    def chat_ok(self) -> bool:
        return self.chat_verdict == "REACHABLE"

    @property
    def call_ok(self) -> bool | None:
        if self.call_verdict == "UNKNOWN":
            return None
        return self.call_verdict == "REACHABLE"


@dataclass
class ScanReport:
    timestamp: str
    results: list[MessengerResult] = field(default_factory=list)
