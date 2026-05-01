"""Tests for the crowdsource store."""
import pytest

from ping_luma.crowdsource import CrowdSourceStore


@pytest.mark.asyncio
async def test_non_iran_country_is_dropped():
    store = CrowdSourceStore(min_samples=1)
    ok = await store.add_sample(
        user_id=1, messenger_id="bale", country="DE",
        chat_ok=True, call_ok=True,
    )
    assert ok is False
    snap = await store.snapshot()
    assert snap == {}


@pytest.mark.asyncio
async def test_disabled_store_drops_everything():
    store = CrowdSourceStore(enabled=False, min_samples=1)
    ok = await store.add_sample(
        user_id=1, messenger_id="bale", country="IR",
        chat_ok=True, call_ok=True,
    )
    assert ok is False
    assert await store.snapshot() == {}


@pytest.mark.asyncio
async def test_below_min_samples_emits_nothing():
    store = CrowdSourceStore(min_samples=3)
    for uid in (1, 2):
        await store.add_sample(
            user_id=uid, messenger_id="bale", country="IR",
            chat_ok=True, call_ok=True,
        )
    assert await store.snapshot() == {}


@pytest.mark.asyncio
async def test_majority_chat_ok_yields_true():
    store = CrowdSourceStore(min_samples=3, success_threshold=0.7, blocked_threshold=0.3)
    for uid in (1, 2, 3, 4):
        await store.add_sample(
            user_id=uid, messenger_id="bale", country="IR",
            chat_ok=True, call_ok=False,
        )
    snap = await store.snapshot()
    assert snap["bale"]["chat_ok"] is True
    assert snap["bale"]["call_ok"] is False


@pytest.mark.asyncio
async def test_dedup_per_user_only_counts_once():
    store = CrowdSourceStore(min_samples=3)
    # Same user spamming three times should NOT satisfy min_samples.
    for _ in range(5):
        await store.add_sample(
            user_id=42, messenger_id="bale", country="IR",
            chat_ok=True, call_ok=True,
        )
    assert await store.snapshot() == {}


@pytest.mark.asyncio
async def test_split_50_50_is_inconclusive():
    store = CrowdSourceStore(min_samples=4, success_threshold=0.7, blocked_threshold=0.3)
    for uid, ok in [(1, True), (2, True), (3, False), (4, False)]:
        await store.add_sample(
            user_id=uid, messenger_id="bale", country="IR",
            chat_ok=ok, call_ok=ok,
        )
    snap = await store.snapshot()
    assert snap.get("bale", {}).get("chat_ok") is None
    assert snap.get("bale", {}).get("call_ok") is None


@pytest.mark.asyncio
async def test_country_filter_is_case_insensitive():
    store = CrowdSourceStore(min_samples=1)
    ok = await store.add_sample(
        user_id=1, messenger_id="bale", country="ir",
        chat_ok=True, call_ok=True,
    )
    assert ok is True


@pytest.mark.asyncio
async def test_ingest_payload_accepts_only_bool_signals():
    store = CrowdSourceStore(min_samples=1)
    payload = {
        "country": "IR",
        "results": [
            {"id": "bale", "chat_ok": True, "call_ok": True},
            {"id": "eitaa", "chat_ok": False, "call_ok": None},  # call_ok stripped
            {"id": "telegram", "chat_ok": None, "call_ok": None},  # nothing useful
            {"chat_ok": True, "call_ok": True},  # missing id
        ],
    }
    accepted = await store.ingest_payload(user_id=99, payload=payload)
    assert accepted == 2
    snap = await store.snapshot()
    assert snap["bale"]["chat_ok"] is True
    assert snap["bale"]["call_ok"] is True
    assert snap["eitaa"]["chat_ok"] is False
    # eitaa.call_ok should be absent (no bool sample contributed)
    assert "call_ok" not in snap["eitaa"]


@pytest.mark.asyncio
async def test_user_hash_is_stable_within_process():
    store = CrowdSourceStore()
    a = store._hash(123)
    b = store._hash(123)
    assert a == b
    assert a != store._hash(124)


@pytest.mark.asyncio
async def test_expired_samples_are_evicted_on_next_add():
    import time
    store = CrowdSourceStore(min_samples=1, max_age_s=1)
    await store.add_sample(
        user_id=1, messenger_id="bale", country="IR",
        chat_ok=True, call_ok=True,
    )
    snap_before = await store.snapshot()
    assert "bale" in snap_before
    time.sleep(1.1)
    # Trigger eviction with a fresh sample for a *different* user.
    await store.add_sample(
        user_id=2, messenger_id="bale", country="IR",
        chat_ok=False, call_ok=False,
    )
    snap_after = await store.snapshot()
    assert snap_after["bale"]["chat_ok"] is False
