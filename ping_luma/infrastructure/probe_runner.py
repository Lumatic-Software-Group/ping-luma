from __future__ import annotations

import socket
import ssl
import struct
import time
import urllib.error
import urllib.request

from ping_luma.domain.messengers import Messenger
from ping_luma.domain.probe_results import (
    DnsResult,
    MessengerResult,
    StunResult,
    TurnResult,
    UrlResult,
)


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
        # 4xx/5xx still proves we reached the origin and TLS is valid.
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
_STUN_TXID = b"\x00" * 12
_STUN_BINDING_REQUEST = struct.pack(">HHI12s", 0x0001, 0x0000, _STUN_MAGIC, _STUN_TXID)
_STUN_SUCCESS_TYPE = 0x0101
_STUN_ERROR_TYPE = 0x0111


def _is_valid_stun_response(data: bytes) -> bool:
    if len(data) < 20:
        return False
    msg_type, _msg_len, magic, txid = struct.unpack(">HHI12s", data[:20])
    if magic != _STUN_MAGIC:
        return False
    if txid != _STUN_TXID:
        return False
    return msg_type in (_STUN_SUCCESS_TYPE, _STUN_ERROR_TYPE)


def _probe_stun_udp(
        host: str, port: int = 3478, timeout: float = 4.0
) -> StunResult:
    """STUN UDP binding probe with strict response validation.

    A reply that fails magic-cookie / transaction-ID validation is treated
    as a failure, not as proof of reachability — that prevents random
    middleboxes from being mistaken for STUN servers.
    """
    t0 = time.perf_counter()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(_STUN_BINDING_REQUEST, (host, port))
            data, _ = sock.recvfrom(1024)
        if not _is_valid_stun_response(data):
            return StunResult(
                host=host, port=port, reachable=False,
                error="invalid STUN response",
            )
        return StunResult(
            host=host, port=port, reachable=True,
            latency_ms=round((time.perf_counter() - t0) * 1000, 1),
        )
    except (socket.timeout, OSError) as exc:
        return StunResult(host=host, port=port, reachable=False,
                          error=str(exc)[:80])


def _probe_turn_tcp(
        host: str, port: int = 3478, timeout: float = 4.0
) -> TurnResult:
    """TCP connect probe to a TURN host, trying STUN/TURN port and TLS port."""
    last_err = ""
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
        url_results: list[UrlResult], dns_results: list[DnsResult],
) -> tuple[int, str]:
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
        stun_results: list[StunResult],
        turn_result: TurnResult | None,
        call_protocol: str,
) -> tuple[int, str]:
    if call_protocol == "proprietary" or not stun_results:
        return 0, "UNKNOWN"

    ok_stun = sum(1 for r in stun_results if r.reachable)
    stun_ratio = ok_stun / max(len(stun_results), 1)
    score = round(stun_ratio * 70)

    if turn_result and turn_result.reachable:
        score += 30

    stun_lats = [r.latency_ms for r in stun_results if r.reachable and r.latency_ms]
    if stun_lats and min(stun_lats) < 200:
        score += 5

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
    chat_score, chat_verdict = _score_messaging(url_results, dns_results)

    latencies = [r.latency_ms for r in url_results if r.reachable and r.latency_ms]

    stun_results: list[StunResult] = []
    if m.call_protocol == "webrtc" and m.stun_hosts:
        stun_results = [_probe_stun_udp(host) for host in m.stun_hosts]

    turn_result: TurnResult | None = None
    if m.turn_host and m.call_protocol == "webrtc":
        turn_result = _probe_turn_tcp(m.turn_host)

    call_score, call_verdict = _score_calls(
        stun_results, turn_result, m.call_protocol,
    )

    return MessengerResult(
        messenger=m,
        chat_score=chat_score,
        chat_verdict=chat_verdict,
        best_latency_ms=min(latencies) if latencies else None,
        url_results=url_results,
        dns_results=dns_results,
        call_score=call_score,
        call_verdict=call_verdict,
        stun_results=stun_results,
        turn_result=turn_result,
    )
