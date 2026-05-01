from __future__ import annotations

import argparse
import json
import logging
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

# Allow `python -m scripts.refresh_asn_map` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ping_luma.asn import classify_from_asn  # noqa: E402
from ping_luma.messengers import MESSENGERS  # noqa: E402

log = logging.getLogger("refresh_asn_map")

BGPVIEW_BASE = "https://api.bgpview.io"


def _collect_hosts() -> set[str]:
    hosts: set[str] = set()
    for m in MESSENGERS:
        if m.turn_host:
            hosts.add(m.turn_host)
        for url in m.probe_urls:
            host = urlparse(url).hostname
            if host:
                hosts.add(host)
    return hosts


def _resolve(host: str) -> str | None:
    try:
        return socket.gethostbyname(host)
    except OSError as exc:
        log.warning("DNS resolve failed for %s: %s", host, exc)
        return None


def _query_bgpview_ip(client: httpx.Client, ip: str) -> dict | None:
    try:
        resp = client.get(f"{BGPVIEW_BASE}/ip/{ip}", timeout=15)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("bgpview /ip/%s failed: %s", ip, exc)
        return None
    payload = resp.json()
    if payload.get("status") != "ok":
        return None
    data = payload.get("data") or {}
    prefixes: list[dict] = data.get("prefixes") or []
    if not prefixes:
        return None
    # Pick the most-specific prefix (longest mask) — that's the AS that
    # actually announces this IP today.
    prefixes.sort(key=lambda p: int((p.get("prefix") or "0/0").split("/")[-1]), reverse=True)
    top = prefixes[0]
    asn = (top.get("asn") or {}).get("asn")
    asn_name = (top.get("asn") or {}).get("name") or (top.get("asn") or {}).get("description") or ""
    country = top.get("country_code") or (top.get("asn") or {}).get("country_code") or ""
    return {"asn": asn, "asn_name": asn_name, "country": country}


def refresh(output: Path) -> None:
    hosts = sorted(_collect_hosts())
    log.info("Refreshing ASN map for %d hosts → %s", len(hosts), output)

    out: dict[str, dict] = {
        "_meta": {
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
            "source": "api.bgpview.io",
            "host_count": len(hosts),
        },
    }

    with httpx.Client() as client:
        for host in hosts:
            ip = _resolve(host)
            if not ip:
                continue
            info = _query_bgpview_ip(client, ip)
            if not info:
                log.info("%-30s %-15s no BGP data", host, ip)
                continue
            classification = classify_from_asn(
                info.get("asn"),
                info.get("asn_name", ""),
                info.get("country", ""),
            )
            out[host] = {
                "ip": ip,
                "asn": info["asn"],
                "asn_name": info["asn_name"],
                "country": info["country"],
                "classification": classification,
            }
            log.info(
                "%-30s %-15s AS%-7s %-12s %s",
                host, ip, info["asn"], info["country"] or "?", classification,
            )
            # bgpview rate-limits ~5 req/s; be polite.
            time.sleep(0.3)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Wrote %d host classifications to %s", len(out) - 1, output)


def main() -> int:
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s",
        level=logging.INFO,
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="ping_luma/asn_map.json",
        help="Path to write the refreshed ASN map (default: ping_luma/asn_map.json)",
    )
    args = parser.parse_args()
    refresh(Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
