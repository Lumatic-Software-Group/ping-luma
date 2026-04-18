import socket
import ssl
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
class MessengerResult:
    messenger: Messenger
    verdict: str  # "REACHABLE" | "PARTIAL" | "BLOCKED"
    score: int  # 0–100
    best_latency_ms: Optional[float] = None
    url_results: List[UrlResult] = field(default_factory=list)
    dns_results: List[DnsResult] = field(default_factory=list)

    @property
    def verdict_icon(self) -> str:
        return {"REACHABLE": "✅", "PARTIAL": "⚠️", "BLOCKED": "❌"}.get(
            self.verdict, "❓"
        )

    @property
    def verdict_label_fa(self) -> str:
        return {
            "REACHABLE": "در دسترس",
            "PARTIAL": "ناپایدار",
            "BLOCKED": "مسدود",
        }.get(self.verdict, "نامشخص")


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


def _probe_url(url: str, timeout: int = 8) -> UrlResult:
    """Perform an HTTPS GET and measure latency. HTTP 4xx/5xx counts as reachable."""
    t0 = time.perf_counter()
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            url, headers={"User-Agent": "PingLuma/1.0 (+https://pingluma.app)"}
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
        # Server replied with an error code — the host is reachable.
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
    """Resolve a hostname and measure latency."""
    t0 = time.perf_counter()
    try:
        ip = socket.gethostbyname(host)
        return DnsResult(
            host=host,
            resolved=True,
            ip=ip,
            latency_ms=round((time.perf_counter() - t0) * 1000, 1),
        )
    except socket.gaierror:
        return DnsResult(host=host, resolved=False)


def _score_messenger(
        url_results: List[UrlResult],
        dns_results: List[DnsResult],
) -> Tuple[int, str]:
    """
    Compute a 0-100 health score and derive a verdict.

    Scoring breakdown:
      - URL reachability: up to 60 pts (proportional to success ratio)
      - DNS resolution:   up to 30 pts (proportional to success ratio)
      - Latency bonus:    +10 pts if best latency < 500 ms
                          + 5 pts if best latency < 1200 ms
    Verdict thresholds:
      >= 70 → REACHABLE
      30-69 → PARTIAL
      <  30 → BLOCKED
    """
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


def _check_one_messenger(m: Messenger) -> MessengerResult:
    """Probe all URLs and DNS hosts for a single messenger and return a result."""
    url_results = [_probe_url(url) for url in m.probe_urls]
    dns_results = [_probe_dns(host) for host in m.dns_hosts]
    score, verdict = _score_messenger(url_results, dns_results)
    latencies = [r.latency_ms for r in url_results if r.reachable and r.latency_ms]
    return MessengerResult(
        messenger=m,
        verdict=verdict,
        score=score,
        best_latency_ms=min(latencies) if latencies else None,
        url_results=url_results,
        dns_results=dns_results,
    )


def run_full_scan(messengers: Optional[List[Messenger]] = None) -> ScanReport:
    """Probe all messengers concurrently and return a consolidated report."""
    targets = messengers or MESSENGERS
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    results: List[Optional[MessengerResult]] = [None] * len(targets)

    with ThreadPoolExecutor(max_workers=len(targets)) as pool:
        futures = {
            pool.submit(_check_one_messenger, m): i
            for i, m in enumerate(targets)
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()

    return ScanReport(timestamp=timestamp, results=results)


def run_quick_ping(messenger_id: str = "bale") -> Tuple[bool, float]:
    """Probe only the first URL of a single messenger. Used for fast sanity checks."""
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


def format_scan_report(report: ScanReport) -> str:
    """Format a full scan report as an HTML Telegram message."""
    lines = [
        "<b>نتیجه بررسی پیام‌رسان‌های ایرانی</b>",
        f"<code>{report.timestamp}</code>",
        "",
    ]

    for r in report.results:
        avail = _AVAILABILITY_LABEL.get(r.messenger.availability, "")
        lat = f"  <code>{r.best_latency_ms:.0f}ms</code>" if r.best_latency_ms else ""
        lines.append(
            f"{r.verdict_icon} <b>{r.messenger.name}</b> ({r.messenger.name_fa})"
            f"  —  {r.verdict_label_fa}{lat}\n"
            f"    {avail}  ·  امتیاز: <code>{r.score}/100</code>"
        )

    total = len(report.results)
    reachable = len(report.reachable)
    blocked = len(report.blocked)

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━",
        f"✅ {reachable}/{total} در دسترس  ·  ❌ {blocked}/{total} مسدود",
        "",
        "<i>نتایج فقط بازتاب‌دهنده وضعیت شبکه شما هستند.</i>",
    ]
    return "\n".join(lines)


def format_messenger_detail(r: MessengerResult) -> str:
    """Format the detailed probe result for a single messenger as HTML."""
    avail = _AVAILABILITY_LABEL.get(r.messenger.availability, "")
    lines = [
        f"{r.verdict_icon} <b>{r.messenger.name}</b> ({r.messenger.name_fa})",
        "",
        f"وضعیت:   <b>{r.verdict_label_fa}</b>",
        f"امتیاز:  <code>{r.score}/100</code>",
        f"دسترسی:  {avail}",
    ]
    if r.best_latency_ms:
        lines.append(f"تأخیر:   <code>{r.best_latency_ms:.0f}ms</code>")

    lines += ["", "<b>سرورها</b>"]
    for u in r.url_results:
        icon = "✅" if u.reachable else "❌"
        lat = f" <code>{u.latency_ms}ms</code>" if u.latency_ms else ""
        lines.append(f"{icon} <code>{u.url}</code>{lat}")

    lines += ["", "<b>DNS</b>"]
    for d in r.dns_results:
        icon = "✅" if d.resolved else "❌"
        ip = f" → <code>{d.ip}</code>" if d.ip else ""
        lines.append(f"{icon} <code>{d.host}</code>{ip}")

    return "\n".join(lines)
