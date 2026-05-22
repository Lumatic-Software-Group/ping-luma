from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger("PingLuma.asn")

CLASSIFICATIONS = {
    "iran_only_structural",
    "iran_likely",
    "cdn_fronted",
    "global",
    "unknown",
}

# AS numbers that route exclusively (or near-exclusively) inside Iran.
# Curated from RIPEstat and APNIC delegated lists. Refresh annually.
IRAN_ONLY_ASNS = frozenset({
    58224,  # Iran Telecommunication Company (TIC)
    31549,  # Aria Shatel
    12880,  # Information Technology Company (ITC)
    25184,  # Afranet
    197207,  # MCCI / Hamrah-e Aval
    39501,  # Pars Online
    41881,  # Datak Telecom
    44244,  # Iranian Net
    48715,  # Pishgaman Toseah Ertebatat
    50810,  # Mobinnet Telecom
    16322,  # Pars Online (legacy ASN)
    24631,  # Sepanta Communication
})

# ASN ranges or names that indicate CDN fronting where origin is opaque.
CDN_ASN_NAMES = (
    "cloudflare", "akamai", "fastly", "amazon", "google", "microsoft", "azure",
    "alibaba", "huawei cloud", "oracle cloud",
)


class AsnMap:
    """In-memory view over a baked ``asn_map.json`` file."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            log.warning(
                "ASN map not found at %s — run scripts/refresh_asn_map.py to bake it.",
                self._path,
            )
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Failed to load ASN map %s: %s", self._path, exc)
            return
        # Strip the optional "_meta" key.
        self._data = {k: v for k, v in raw.items() if k != "_meta" and isinstance(v, dict)}
        log.info("Loaded ASN map for %d hosts from %s", len(self._data), self._path)

    def lookup(self, host: str | None) -> dict | None:
        if not host:
            return None
        return self._data.get(host)

    def classify(self, host: str | None) -> str:
        entry = self.lookup(host)
        if not entry:
            return "unknown"
        cls = entry.get("classification", "unknown")
        return cls if cls in CLASSIFICATIONS else "unknown"

    def __len__(self) -> int:
        return len(self._data)


def classify_from_asn(asn: int | None, asn_name: str, country: str) -> str:
    """Given raw whois/bgp fields, return a normalised classification.

    Used by the offline refresh script and unit tests.
    """
    if asn and asn in IRAN_ONLY_ASNS:
        return "iran_only_structural"
    name = (asn_name or "").lower()
    if any(needle in name for needle in CDN_ASN_NAMES):
        return "cdn_fronted"
    if (country or "").upper() == "IR":
        return "iran_likely"
    return "global"
