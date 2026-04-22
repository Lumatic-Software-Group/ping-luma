import socket
import ssl
import struct
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from ping_luma.messengers import MESSENGERS, Messenger


@dataclass
class UrlResult:
    url: str
    reachable: bool
    latency_ms: Optional[float] = None
    status_code: Optional[int] = None
    ssl_valid: bool = False
    error: Optional[str] = None


@dataclass
class DnsResult:
    host: str
    resolved: bool
    ip: Optional[str] = None
    latency_ms: Optional[float] = None


@dataclass
class StunResult:
    host: str
    port: int
    reachable: bool
    latency_ms: Optional[float] = None
    via_tcp: bool = False
    error: Optional[str] = None


@dataclass
class TurnResult:
    host: str
    port: int
    reachable: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None


@dataclass
class MessengerResult:
    messenger: Messenger
    msg_verdict: str
    msg_score: int
    best_latency_ms: Optional[float] = None
    url_results: List[UrlResult] = field(default_factory=list)
    dns_results: List[DnsResult] = field(default_factory=list)
    call_verdict: str = "UNKNOWN"
    call_score: int = 0
    stun_results: List[StunResult] = field(default_factory=list)
    turn_result: Optional[TurnResult] = None

    @property
    def verdict(self) -> str:
        if self.call_verdict == "UNKNOWN":
            return self.msg_verdict
        order = {"BLOCKED": 0, "PARTIAL": 1, "REACHABLE": 2}
        combined = min(
            order.get(self.msg_verdict, 1),
            order.get(self.call_verdict, 1),
        )
        return ["BLOCKED", "PARTIAL", "REACHABLE"][combined]

    @property
    def score(self) -> int:
        if self.call_verdict == "UNKNOWN":
            return self.msg_score
        return min(self.msg_score, self.call_score)

    @property
    def verdict_icon(self) -> str:
        return {"REACHABLE": "✅", "PARTIAL": "⚠️", "BLOCKED": "❌",
                "UNKNOWN": "❓"}.get(self.verdict, "❓")

    @property
    def verdict_label_fa(self) -> str:
        return {
            "REACHABLE": "در دسترس",
            "PARTIAL": "ناپایدار",
            "BLOCKED": "مسدود",
            "UNKNOWN": "نامشخص",
        }.get(self.verdict, "نامشخص")

    @property
    def call_verdict_icon(self) -> str:
        return {"REACHABLE": "✅", "PARTIAL": "⚠️", "BLOCKED": "❌",
                "UNKNOWN": "❓"}.get(self.call_verdict, "❓")

    @property
    def call_verdict_label_fa(self) -> str:
        return {
            "REACHABLE": "تماس ممکن",
            "PARTIAL": "تماس ناپایدار",
            "BLOCKED": "تماس مسدود",
            "UNKNOWN": "قابل تست نیست",
        }.get(self.call_verdict, "نامشخص")


@dataclass
class ScanReport:
    timestamp: str
    results: List[MessengerResult] = field(default_factory=list)

    @property
    def reachable(self) -> List[MessengerResult]:
        return [r for r in self.results if r.verdict == "REACHABLE"]

    @property
    def partial(self) -> List[MessengerResult]:
        return [r for r in self.results if r.verdict == "PARTIAL"]

    @property
    def blocked(self) -> List[MessengerResult]:
        return [r for r in self.results if r.verdict == "BLOCKED"]

    @property
    def calls_reachable(self) -> List[MessengerResult]:
        return [r for r in self.results if r.call_verdict == "REACHABLE"]

    @property
    def calls_blocked(self) -> List[MessengerResult]:
        return [r for r in self.results if r.call_verdict == "BLOCKED"]


def _probe_url(url: str, timeout: int = 8) -> UrlResult:
    t0 = time.perf_counter()
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            url, headers={"User-Agent": "PingLuma/2.0 (+https://pingluma.app)"}
        )
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return UrlResult(
                url=url,
                reachable=True,
                latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                status_code=resp.status,
                ssl_valid=True,
            )
    except urllib.error.HTTPError as exc:
        return UrlResult(
            url=url,
            reachable=True,
            latency_ms=round((time.perf_counter() - t0) * 1000, 1),
            status_code=exc.code,
            ssl_valid=True,
        )
    except ssl.SSLError as exc:
        return UrlResult(url=url, reachable=False, ssl_valid=False,
                         error=f"SSL: {exc}")
    except (urllib.error.URLError, socket.timeout, OSError) as exc:
        return UrlResult(url=url, reachable=False, error=str(exc)[:120])


def _probe_dns(host: str) -> DnsResult:
    t0 = time.perf_counter()
    try:
        ip = socket.gethostbyname(host)
        return DnsResult(
            host=host, resolved=True, ip=ip,
            latency_ms=round((time.perf_counter() - t0) * 1000, 1),
        )
    except socket.gaierror:
        return DnsResult(host=host, resolved=False)


_STUN_MAGIC = 0x2112A442
_STUN_BINDING_REQUEST = struct.pack(
    ">HHI12s", 0x0001, 0x0000, _STUN_MAGIC, b"\x00" * 12,
)
_STUN_SUCCESS_TYPE = 0x0101


def _probe_stun_udp(host: str, port: int = 3478, timeout: float = 4.0) -> StunResult:
    t0 = time.perf_counter()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(_STUN_BINDING_REQUEST, (host, port))
            data, _ = sock.recvfrom(1024)
            elapsed = round((time.perf_counter() - t0) * 1000, 1)
            return StunResult(host=host, port=port, reachable=True,
                              latency_ms=elapsed)
    except (socket.timeout, OSError):
        pass

    t0 = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.sendall(_STUN_BINDING_REQUEST)
            try:
                sock.recv(1024)
            except socket.timeout:
                pass
            elapsed = round((time.perf_counter() - t0) * 1000, 1)

            return StunResult(host=host, port=port, reachable=True,
                              latency_ms=elapsed, via_tcp=True)
    except (socket.timeout, OSError) as exc:
        return StunResult(host=host, port=port, reachable=False,
                          error=str(exc)[:80])


def _probe_turn_tcp(host: str, port: int = 3478, timeout: float = 4.0) -> TurnResult:
    for p in (port, 5349):
        t0 = time.perf_counter()
        try:
            with socket.create_connection((host, p), timeout=timeout):
                return TurnResult(
                    host=host, port=p, reachable=True,
                    latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                )
        except (socket.timeout, OSError) as exc:
            last_err = str(exc)[:80]

    return TurnResult(host=host, port=port, reachable=False, error=last_err)


def _score_messaging(
        url_results: List[UrlResult],
        dns_results: List[DnsResult],
) -> Tuple[int, str]:
    ok_urls = sum(1 for r in url_results if r.reachable)
    ok_dns = sum(1 for r in dns_results if r.resolved)
    url_ratio = ok_urls / max(len(url_results), 1)
    dns_ratio = ok_dns / max(len(dns_results), 1)
    score = round(url_ratio * 60 + dns_ratio * 30)

    latencies = [r.latency_ms for r in url_results if r.reachable and r.latency_ms]
    if latencies:
        best = min(latencies)
        score += 10 if best < 500 else 5 if best < 1200 else 0

    score = min(100, score)
    verdict = (
        "REACHABLE" if score >= 70
        else "PARTIAL" if score >= 30
        else "BLOCKED"
    )
    return score, verdict


def _score_calls(
        stun_results: List[StunResult],
        turn_result: Optional[TurnResult],
        call_protocol: str,
) -> Tuple[int, str]:
    if call_protocol == "proprietary" or not stun_results:
        return 0, "UNKNOWN"

    ok_stun = sum(1 for r in stun_results if r.reachable)
    stun_ratio = ok_stun / max(len(stun_results), 1)
    score = round(stun_ratio * 70)

    if turn_result and turn_result.reachable:
        score += 30

    stun_lats = [r.latency_ms for r in stun_results if r.reachable and r.latency_ms]
    if stun_lats:
        score += 5 if min(stun_lats) < 200 else 0

    score = min(100, score)
    verdict = (
        "REACHABLE" if score >= 70
        else "PARTIAL" if score >= 30
        else "BLOCKED"
    )
    return score, verdict


def _check_one_messenger(m: Messenger) -> MessengerResult:
    url_results = [_probe_url(url) for url in m.probe_urls]
    dns_results = [_probe_dns(host) for host in m.dns_hosts]
    msg_score, msg_verdict = _score_messaging(url_results, dns_results)

    latencies = [r.latency_ms for r in url_results if r.reachable and r.latency_ms]

    stun_results: List[StunResult] = []
    if m.call_protocol == "webrtc" and m.stun_hosts:
        stun_results = [_probe_stun_udp(host) for host in m.stun_hosts]

    turn_result: Optional[TurnResult] = None
    if m.turn_host and m.call_protocol == "webrtc":
        turn_result = _probe_turn_tcp(m.turn_host)

    call_score, call_verdict = _score_calls(
        stun_results, turn_result, m.call_protocol
    )

    return MessengerResult(
        messenger=m,
        msg_verdict=msg_verdict,
        msg_score=msg_score,
        best_latency_ms=min(latencies) if latencies else None,
        url_results=url_results,
        dns_results=dns_results,
        call_verdict=call_verdict,
        call_score=call_score,
        stun_results=stun_results,
        turn_result=turn_result,
    )


def run_full_scan(messengers: Optional[List[Messenger]] = None) -> ScanReport:
    targets = messengers or MESSENGERS
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    results: List[Optional[MessengerResult]] = [None] * len(targets)

    with ThreadPoolExecutor(max_workers=len(targets)) as pool:
        futures = {pool.submit(_check_one_messenger, m): i
                   for i, m in enumerate(targets)}
        for future in as_completed(futures):
            results[futures[future]] = future.result()

    return ScanReport(timestamp=timestamp, results=results)


def run_quick_ping(messenger_id: str = "bale") -> Tuple[bool, float]:
    from ping_luma.messengers import MESSENGER_BY_ID

    m = MESSENGER_BY_ID.get(messenger_id)
    if not m:
        return False, 0.0
    result = _probe_url(m.probe_urls[0], timeout=6)
    return result.reachable, result.latency_ms or 0.0


_AVAILABILITY_LABEL: dict = {
    "global": "در دسترس جهانی",
    "mixed": "دسترسی ترکیبی",
    "iran": "مخصوص ایران",
}

_CALL_OUTSIDE_LABEL: dict = {
    "yes": "✅ تماس بدون VPN",
    "partial": "⚠️ تماس ناپایدار",
    "vpn": "🔒 نیاز به VPN ایرانی",
    "no": "❌ تماس مسدود",
    "unknown": "❓ نامشخص",
}


def format_scan_report(report: ScanReport) -> str:
    """Concise scan report for Telegram — no technical scores or server details."""
    lines = [
        "<b>نتیجه بررسی پیام‌رسان‌های ایرانی</b>",
        f"<code>{report.timestamp}</code>",
        "",
    ]

    for r in report.results:
        call_l = _CALL_OUTSIDE_LABEL.get(r.messenger.call_outside_iran, "❓")
        lat = (f"  <code>{r.best_latency_ms:.0f}ms</code>"
               if r.best_latency_ms else "")
        lines.append(
            f"{r.verdict_icon} <b>{r.messenger.name}</b> ({r.messenger.name_fa})"
            f"  —  {r.verdict_label_fa}{lat}\n"
            f"    📞 {call_l}"
        )

    total = len(report.results)
    msg_ok = len(report.reachable)
    call_ok = len(report.calls_reachable)

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━",
        f"💬 پیام: {msg_ok}/{total} در دسترس",
        f"📞 تماس: {call_ok}/{total} قابل برقراری",
        "",
        "<i>برای بررسی دقیق از شبکه خودتان، داشبورد وب را باز کنید.</i>",
    ]
    return "\n".join(lines)


def format_messenger_detail(r: MessengerResult) -> str:
    """Simple per-messenger detail for Telegram — user-facing only."""
    call_l = _CALL_OUTSIDE_LABEL.get(r.messenger.call_outside_iran, "❓")
    vpn_note = ("هر VPN کافی است ✅"
                if r.messenger.call_vpn_any
                else "فقط VPN با خروجی ایرانی ⚠️")
    reg_note = {
        "yes": "✅ ثبت‌نام از خارج ممکن است",
        "no": "❌ ثبت‌نام از خارج مسدود است",
        "sms": "📱 نیاز به شماره موبایل ایرانی",
    }.get(r.messenger.registration_outside_iran, "❓")

    lines = [
        f"{r.verdict_icon} <b>{r.messenger.name}</b> ({r.messenger.name_fa})",
        "",
        f"💬 پیام‌رسانی:  <b>{r.verdict_label_fa}</b>",
        f"📞 تماس:        {call_l}",
        f"🔒 با VPN:      {vpn_note}",
        f"📝 ثبت‌نام:     {reg_note}",
    ]

    if r.best_latency_ms:
        lines.append(f"⏱ تأخیر:       <code>{r.best_latency_ms:.0f}ms</code>")

    if r.messenger.call_notes:
        lines += ["", f"<i>{r.messenger.call_notes}</i>"]

    return "\n".join(lines)
