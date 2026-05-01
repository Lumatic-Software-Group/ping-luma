"""Tests for the Iran-reference façade (ASN + OONI + Crowd + HTTP)."""
import json
from pathlib import Path

import pytest

from ping_luma.asn import AsnMap
from ping_luma.crowdsource import CrowdSourceStore
from ping_luma.iran_reference import IranReferenceClient
from ping_luma.ooni import OoniClient


# ---------- helpers ---------------------------------------------------------

def _make_asn_map(tmp_path: Path, entries: dict) -> AsnMap:
    p = tmp_path / "asn_map.json"
    p.write_text(json.dumps({"_meta": {}, **entries}))
    return AsnMap(p)


class _StubOoni(OoniClient):
    """OONI client that returns scripted verdicts per host."""

    def __init__(self, scripted: dict):
        super().__init__(enabled=True)
        self._scripted = scripted

    async def is_reachable_from_iran(self, host):  # type: ignore[override]
        return self._scripted.get(host)


# ---------- unconfigured ----------------------------------------------------

@pytest.mark.asyncio
async def test_completely_unconfigured_client_returns_unknowns():
    client = IranReferenceClient()
    assert client.configured is False
    result = await client.refresh()
    # Unconfigured: no sources, so refresh returns the empty cache (i.e. {}).
    assert result == {}


# ---------- ASN-only --------------------------------------------------------

@pytest.mark.asyncio
async def test_asn_iran_only_sets_call_ok_true(tmp_path: Path):
    asn_map = _make_asn_map(tmp_path, {
        "turn.eitaa.com": {
            "ip": "5.0.0.1", "asn": 58224, "asn_name": "TIC",
            "country": "IR", "classification": "iran_only_structural",
        },
    })
    client = IranReferenceClient(asn_map=asn_map)
    assert client.configured is True
    result = await client.refresh()
    assert result["eitaa"]["call_ok"] is True
    # No chat verdict from ASN alone.
    assert result["eitaa"]["chat_ok"] is None


@pytest.mark.asyncio
async def test_asn_cdn_does_not_override(tmp_path: Path):
    asn_map = _make_asn_map(tmp_path, {
        "turn.bale.ai": {
            "ip": "104.16.0.1", "asn": 13335, "asn_name": "Cloudflare",
            "country": "US", "classification": "cdn_fronted",
        },
    })
    client = IranReferenceClient(asn_map=asn_map)
    result = await client.refresh()
    # CDN-fronted gives no Iran-side verdict.
    assert result["bale"] == {"chat_ok": None, "call_ok": None}


# ---------- HTTP override ---------------------------------------------------

@pytest.mark.asyncio
async def test_http_override_wins_over_asn(monkeypatch, tmp_path: Path):
    asn_map = _make_asn_map(tmp_path, {})

    class _OkResp:
        def raise_for_status(self): pass

        def json(self):
            return {"results": {"bale": {"chat_ok": True, "call_ok": True}}}

    class _OkClient:
        def __init__(self, *_a, **_kw): pass

        async def __aenter__(self): return self

        async def __aexit__(self, *exc): return False

        async def get(self, *_a, **_kw): return _OkResp()

    monkeypatch.setattr("ping_luma.iran_reference.httpx.AsyncClient", _OkClient)

    client = IranReferenceClient(asn_map=asn_map, http_url="https://override/ref")
    result = await client.refresh()
    assert result["bale"]["chat_ok"] is True
    assert result["bale"]["call_ok"] is True


@pytest.mark.asyncio
async def test_http_failure_is_swallowed(monkeypatch):
    class _RaisingClient:
        def __init__(self, *_a, **_kw): pass

        async def __aenter__(self): return self

        async def __aexit__(self, *exc): return False

        async def get(self, *_a, **_kw):
            raise RuntimeError("network down")

    monkeypatch.setattr("ping_luma.iran_reference.httpx.AsyncClient", _RaisingClient)

    client = IranReferenceClient(http_url="https://override/ref")
    result = await client.refresh()
    assert all(v == {"chat_ok": None, "call_ok": None} for v in result.values())


# ---------- caching ---------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_within_ttl_avoids_duplicate_ooni_calls():
    calls = {"n": 0}

    class _CountingOoni(_StubOoni):
        async def is_reachable_from_iran(self, host):  # type: ignore[override]
            calls["n"] += 1
            return True

    ooni = _CountingOoni({})
    client = IranReferenceClient(ooni=ooni, ttl_s=300)
    await client.refresh()
    first = calls["n"]
    await client.refresh()
    assert calls["n"] == first, "second refresh within TTL should hit cache"
    await client.refresh(force=True)
    assert calls["n"] > first, "force=True must bypass cache"


# ---------- OONI ------------------------------------------------------------

@pytest.mark.asyncio
async def test_ooni_sets_chat_verdict():
    ooni = _StubOoni({"tapi.bale.ai": True, "eitaa.com": False})
    client = IranReferenceClient(ooni=ooni)
    result = await client.refresh()
    assert result["bale"]["chat_ok"] is True
    assert result["eitaa"]["chat_ok"] is False
    # OONI never sets call verdicts (no WebRTC).
    assert result["bale"]["call_ok"] is None
    assert result["eitaa"]["call_ok"] is None


# ---------- Crowdsource -----------------------------------------------------

@pytest.mark.asyncio
async def test_crowdsource_overrides_ooni():
    ooni = _StubOoni({"tapi.bale.ai": True})
    crowd = CrowdSourceStore(min_samples=3)
    client = IranReferenceClient(ooni=ooni, crowdsource=crowd)
    for uid in (1, 2, 3):
        await crowd.add_sample(
            user_id=uid, messenger_id="bale", country="IR",
            chat_ok=False, call_ok=False,
        )
    result = await client.refresh()
    assert result["bale"]["chat_ok"] is False
    assert result["bale"]["call_ok"] is False


@pytest.mark.asyncio
async def test_http_override_wins_over_crowdsource(monkeypatch):
    crowd = CrowdSourceStore(min_samples=3)
    for uid in (1, 2, 3):
        await crowd.add_sample(
            user_id=uid, messenger_id="bale", country="IR",
            chat_ok=False, call_ok=False,
        )

    class _OkResp:
        def raise_for_status(self): pass

        def json(self):
            return {"results": {"bale": {"chat_ok": True, "call_ok": True}}}

    class _OkClient:
        def __init__(self, *_a, **_kw): pass

        async def __aenter__(self): return self

        async def __aexit__(self, *exc): return False

        async def get(self, *_a, **_kw): return _OkResp()

    monkeypatch.setattr("ping_luma.iran_reference.httpx.AsyncClient", _OkClient)

    client = IranReferenceClient(http_url="https://op/", crowdsource=crowd)
    result = await client.refresh()
    assert result["bale"]["chat_ok"] is True
    assert result["bale"]["call_ok"] is True


@pytest.mark.asyncio
async def test_crowdsource_below_threshold_is_silent():
    ooni = _StubOoni({"tapi.bale.ai": True})
    crowd = CrowdSourceStore(min_samples=3)
    client = IranReferenceClient(ooni=ooni, crowdsource=crowd)
    for uid in (1, 2):
        await crowd.add_sample(
            user_id=uid, messenger_id="bale", country="IR",
            chat_ok=False, call_ok=False,
        )
    result = await client.refresh()
    # OONI verdict survives because crowd < min_samples.
    assert result["bale"]["chat_ok"] is True


@pytest.mark.asyncio
async def test_crowdsource_is_evaluated_live_not_cached():
    """Crowd snapshot must reflect samples added AFTER cache was populated."""
    ooni = _StubOoni({})
    crowd = CrowdSourceStore(min_samples=3)
    client = IranReferenceClient(ooni=ooni, crowdsource=crowd, ttl_s=3600)

    await client.refresh()  # warm cache with no crowd samples

    for uid in (10, 11, 12):
        await crowd.add_sample(
            user_id=uid, messenger_id="bale", country="IR",
            chat_ok=True, call_ok=True,
        )

    result = await client.refresh()
    assert result["bale"]["chat_ok"] is True
    assert result["bale"]["call_ok"] is True


# ---------- Full chain ------------------------------------------------------

@pytest.mark.asyncio
async def test_full_authority_chain_layers_correctly(tmp_path: Path):
    """ASN < OONI < Crowd < HTTP — verify each layer in one run."""
    asn_map = _make_asn_map(tmp_path, {
        "turn.eitaa.com": {
            "ip": "5.0.0.1", "asn": 58224, "asn_name": "TIC",
            "country": "IR", "classification": "iran_only_structural",
        },
    })
    # OONI says Eitaa chat is blocked.
    ooni = _StubOoni({"eitaa.com": False})
    # Crowd overrides OONI: real Iranian users say Eitaa chat is reachable.
    crowd = CrowdSourceStore(min_samples=3)
    for uid in (1, 2, 3):
        await crowd.add_sample(
            user_id=uid, messenger_id="eitaa", country="IR",
            chat_ok=True, call_ok=False,
        )

    client = IranReferenceClient(asn_map=asn_map, ooni=ooni, crowdsource=crowd)
    result = await client.refresh()

    # Eitaa: ASN said call_ok=True; OONI said chat False; Crowd said chat True,
    # call False. Final: chat=True (crowd), call=False (crowd > ASN).
    assert result["eitaa"]["chat_ok"] is True
    assert result["eitaa"]["call_ok"] is False
