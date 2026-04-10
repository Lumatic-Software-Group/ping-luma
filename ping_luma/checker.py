"""
ping_luma/checker.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Core connectivity engine.
Probes all Bale endpoints, resolves DNS, validates SSL,
measures latency, and computes a 0-100 health score.
"""

import socket
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

# ── Endpoints ─────────────────────────────────────────────────────────────────
BALE_ENDPOINTS: Dict[str, Tuple[str, int]] = {
    "سرور API":    ("https://tapi.bale.ai", 443),
    "وب‌اپ":       ("https://web.bale.ai",  443),
    "CDN / رسانه": ("https://cdn.bale.ai",  443),
    "مستندات":     ("https://dev.bale.ai",  443),
}

BALE_DNS_HOSTS: List[str] = [
    "tapi.bale.ai",
    "web.bale.ai",
    "cdn.bale.ai",
]

# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class EndpointResult:
    name: str
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
    error: Optional[str] = None


@dataclass
class CheckReport:
    timestamp: str
    overall_status: str          # "ONLINE" | "DEGRADED" | "OFFLINE"
    score: int                   # 0–100
    endpoints: List[EndpointResult] = field(default_factory=list)
    dns_results: List[DnsResult] = field(default_factory=list)
    vpn_recommended: bool = False
    summary: str = ""
    advice: str = ""

# ── Probes ────────────────────────────────────────────────────────────────────

def check_dns(host: str) -> DnsResult:
    t0 = time.perf_counter()
    try:
        ip = socket.gethostbyname(host)
        return DnsResult(
            host=host, resolved=True, ip=ip,
            latency_ms=round((time.perf_counter() - t0) * 1000, 1),
        )
    except socket.gaierror as exc:
        return DnsResult(host=host, resolved=False, error=str(exc))


def check_endpoint(name: str, url: str, timeout: int = 8) -> EndpointResult:
    t0 = time.perf_counter()
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            url, headers={"User-Agent": "BaleChecker/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return EndpointResult(
                name=name, url=url, reachable=True,
                latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                status_code=resp.status, ssl_valid=True,
            )
    except urllib.error.HTTPError as exc:
        # 4xx/5xx still means the host is reachable
        return EndpointResult(
            name=name, url=url, reachable=True,
            latency_ms=round((time.perf_counter() - t0) * 1000, 1),
            status_code=exc.code, ssl_valid=True,
        )
    except ssl.SSLError as exc:
        return EndpointResult(
            name=name, url=url, reachable=False,
            ssl_valid=False, error=f"SSL: {exc}",
        )
    except (urllib.error.URLError, socket.timeout, OSError) as exc:
        return EndpointResult(name=name, url=url, reachable=False, error=str(exc))

# ── Scoring ───────────────────────────────────────────────────────────────────

def _score(endpoints: List[EndpointResult], dns: List[DnsResult]) -> int:
    ep_pts  = sum(1 for r in endpoints if r.reachable)
    dns_pts = sum(1 for r in dns       if r.resolved)
    base    = round((ep_pts / max(len(endpoints), 1)) * 55
                    + (dns_pts / max(len(dns), 1)) * 25)
    api = next((r for r in endpoints if "API" in r.name), None)
    bonus = 0
    if api and api.latency_ms:
        bonus = 20 if api.latency_ms < 400 else 10 if api.latency_ms < 800 else 0
    return min(100, base + bonus)


def _verdict(score: int) -> Tuple[str, str, str, bool]:
    if score >= 75:
        return (
            "ONLINE",
            "✅ بله به طور کامل در دسترس است.",
            "می‌توانید پیام بفرستید و تماس بگیرید.",
            False,
        )
    elif score >= 40:
        return (
            "DEGRADED",
            "⚠️ اتصال ناپایدار — برخی سرویس‌ها ممکن است کار نکنند.",
            "برخی قابلیت‌ها مانند تماس تصویری ممکن است با مشکل مواجه شوند.",
            True,
        )
    else:
        return (
            "OFFLINE",
            "🔴 بله از این شبکه در دسترس نیست.",
            "در حال حاضر اتصال به بله برقرار نشد.",
            True,
        )

# ── Public API ────────────────────────────────────────────────────────────────

def run_full_check() -> CheckReport:
    """Run all probes synchronously and return a CheckReport."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    dns_results = [check_dns(h) for h in BALE_DNS_HOSTS]
    ep_results  = [
        check_endpoint(name, url)
        for name, (url, _) in BALE_ENDPOINTS.items()
    ]
    score  = _score(ep_results, dns_results)
    status, summary, advice, vpn_rec = _verdict(score)
    return CheckReport(
        timestamp=ts,
        overall_status=status,
        score=score,
        endpoints=ep_results,
        dns_results=dns_results,
        vpn_recommended=vpn_rec,
        summary=summary,
        advice=advice,
    )


def run_quick_ping() -> Tuple[bool, float]:
    """Ping only the API gateway. Returns (reachable, latency_ms)."""
    r = check_endpoint("سرور API", "https://tapi.bale.ai", timeout=6)
    return r.reachable, r.latency_ms or 0.0


def report_to_text(r: CheckReport) -> str:
    """Format a CheckReport as a Markdown bot message (Persian)."""
    badge = {"ONLINE": "🟢", "DEGRADED": "🟡", "OFFLINE": "🔴"}.get(
        r.overall_status, "⚪"
    )
    lines = [
        "*بررسی اتصال بله*",
        f"🕐 `{r.timestamp}`",
        "",
        f"{badge} *وضعیت: {r.overall_status}* — امتیاز {r.score}/100",
        "",
        "*سرورها*",
    ]
    for ep in r.endpoints:
        icon = "✅" if ep.reachable else "❌"
        lat  = f" — `{ep.latency_ms}ms`" if ep.latency_ms else ""
        lines.append(f"{icon} {ep.name}{lat}")

    lines += ["", "*DNS*"]
    for d in r.dns_results:
        icon = "✅" if d.resolved else "❌"
        ip   = f" ← `{d.ip}`" if d.ip else ""
        lines.append(f"{icon} `{d.host}`{ip}")

    lines += ["", f"📋 {r.summary}", "", f"💡 {r.advice}"]
    return "\n".join(lines)
