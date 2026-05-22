"""ASN classifier tests."""
import json
from pathlib import Path

from ping_luma.infrastructure.asn import (
    CDN_ASN_NAMES,
    IRAN_ONLY_ASNS,
    AsnMap,
    classify_from_asn,
)


def test_classify_iran_only_asn_wins():
    assert classify_from_asn(58224, "TIC", "IR") == "iran_only_structural"
    # Even if ASN is Iran-only, that label takes priority over any name.
    assert classify_from_asn(31549, "Aria Shatel", "IR") == "iran_only_structural"


def test_classify_cdn_by_name():
    assert classify_from_asn(13335, "Cloudflare, Inc.", "US") == "cdn_fronted"
    assert classify_from_asn(20940, "Akamai International B.V.", "DE") == "cdn_fronted"
    assert classify_from_asn(54113, "Fastly, Inc.", "US") == "cdn_fronted"


def test_classify_cdn_name_overrides_iran_country():
    # If a host is CDN-fronted, country=IR is meaningless (it's the CDN edge).
    assert classify_from_asn(13335, "Cloudflare", "IR") == "cdn_fronted"


def test_classify_iran_likely_when_country_only():
    # ASN not in our Iran-only set, but country = IR ⇒ soft positive.
    assert classify_from_asn(99999, "Some Iranian ISP", "IR") == "iran_likely"


def test_classify_cloud_providers_treated_as_cdn():
    # Hyperscalers can also front origin → routing tells us nothing.
    assert classify_from_asn(16509, "Amazon", "US") == "cdn_fronted"
    assert classify_from_asn(15169, "Google LLC", "US") == "cdn_fronted"


def test_classify_global_default():
    assert classify_from_asn(3320, "Deutsche Telekom AG", "DE") == "global"


def test_classify_unknown_falls_back_to_global():
    assert classify_from_asn(None, "", "") == "global"


def test_iran_only_set_is_nonempty_and_unique():
    assert len(IRAN_ONLY_ASNS) >= 5
    # frozenset deduplicates by definition
    assert isinstance(IRAN_ONLY_ASNS, frozenset)


def test_cdn_names_are_lowercase():
    for n in CDN_ASN_NAMES:
        assert n == n.lower()


def test_asn_map_missing_file_is_silent(tmp_path: Path):
    # No file: classify always returns "unknown", lookup returns None.
    m = AsnMap(tmp_path / "nope.json")
    assert len(m) == 0
    assert m.classify("turn.eitaa.com") == "unknown"
    assert m.lookup("turn.eitaa.com") is None


def test_asn_map_loads_and_classifies(tmp_path: Path):
    payload = {
        "_meta": {"refreshed_at": "2026-04-28T12:00:00Z"},
        "turn.eitaa.com": {
            "ip": "5.160.1.1",
            "asn": 58224,
            "asn_name": "TIC",
            "country": "IR",
            "classification": "iran_only_structural",
        },
        "turn.bale.ai": {
            "ip": "104.16.0.1",
            "asn": 13335,
            "asn_name": "Cloudflare",
            "country": "US",
            "classification": "cdn_fronted",
        },
    }
    p = tmp_path / "asn_map.json"
    p.write_text(json.dumps(payload))

    m = AsnMap(p)
    assert len(m) == 2
    assert m.classify("turn.eitaa.com") == "iran_only_structural"
    assert m.classify("turn.bale.ai") == "cdn_fronted"
    assert m.classify("turn.unknown.com") == "unknown"
    assert m.lookup("turn.eitaa.com")["asn"] == 58224


def test_asn_map_normalises_unknown_classification(tmp_path: Path):
    payload = {
        "h": {"ip": "1.2.3.4", "asn": 1, "asn_name": "x", "country": "X",
              "classification": "totally-bogus"},
    }
    p = tmp_path / "asn_map.json"
    p.write_text(json.dumps(payload))
    m = AsnMap(p)
    assert m.classify("h") == "unknown"


def test_asn_map_handles_corrupt_json(tmp_path: Path):
    p = tmp_path / "asn_map.json"
    p.write_text("{ this is not json")
    m = AsnMap(p)  # must not raise
    assert len(m) == 0
    assert m.classify("anything") == "unknown"
