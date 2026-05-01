"""Tests for the OONI aggregation client."""
import pytest

from ping_luma.ooni import OoniClient


# --- helpers ---------------------------------------------------------------

class _Resp:
    def __init__(self, payload, status=200):
        self._p = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._p


def _client_with(payload, monkeypatch, *, count=None):
    """Patch httpx.AsyncClient so .get() returns ``payload``.

    If ``count`` is provided, mutate it in place to count GET calls."""

    class _MockClient:
        def __init__(self, *_a, **_kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, *_a, **_kw):
            if count is not None:
                count["n"] += 1
            return _Resp(payload)

    monkeypatch.setattr("ping_luma.ooni.httpx.AsyncClient", _MockClient)


# --- configured / disabled --------------------------------------------------

def test_disabled_client_is_not_configured():
    c = OoniClient(enabled=False)
    assert c.configured is False


def test_default_client_is_configured():
    c = OoniClient()
    assert c.configured is True


# --- verdict mapping --------------------------------------------------------

@pytest.mark.asyncio
async def test_high_ok_rate_returns_true(monkeypatch):
    payload = {"result": [{
        "ok_count": 90, "anomaly_count": 5, "confirmed_count": 0, "measurement_count": 100,
    }]}
    _client_with(payload, monkeypatch)
    c = OoniClient(success_threshold=0.7, confirmed_blocked_threshold=0.5, min_measurements=3)
    assert await c.is_reachable_from_iran("eitaa.com") is True


@pytest.mark.asyncio
async def test_high_confirmed_rate_returns_false(monkeypatch):
    payload = {"result": [{
        "ok_count": 10, "anomaly_count": 30, "confirmed_count": 60, "measurement_count": 100,
    }]}
    _client_with(payload, monkeypatch)
    c = OoniClient(success_threshold=0.7, confirmed_blocked_threshold=0.5, min_measurements=3)
    assert await c.is_reachable_from_iran("blocked.example") is False


@pytest.mark.asyncio
async def test_mixed_returns_inconclusive(monkeypatch):
    payload = {"result": [{
        "ok_count": 50, "anomaly_count": 30, "confirmed_count": 20, "measurement_count": 100,
    }]}
    _client_with(payload, monkeypatch)
    c = OoniClient(success_threshold=0.7, confirmed_blocked_threshold=0.5, min_measurements=3)
    assert await c.is_reachable_from_iran("uncertain.example") is None


@pytest.mark.asyncio
async def test_below_min_measurements_returns_none(monkeypatch):
    payload = {"result": [{
        "ok_count": 2, "anomaly_count": 0, "confirmed_count": 0, "measurement_count": 2,
    }]}
    _client_with(payload, monkeypatch)
    c = OoniClient(min_measurements=3)
    assert await c.is_reachable_from_iran("rare.example") is None


@pytest.mark.asyncio
async def test_empty_result_list_returns_none(monkeypatch):
    _client_with({"result": []}, monkeypatch)
    c = OoniClient()
    assert await c.is_reachable_from_iran("nodata.example") is None


@pytest.mark.asyncio
async def test_dict_result_form_is_supported(monkeypatch):
    # Some endpoints return result as a single object instead of a list.
    payload = {"result": {
        "ok_count": 80, "anomaly_count": 5, "confirmed_count": 0, "measurement_count": 100,
    }}
    _client_with(payload, monkeypatch)
    c = OoniClient()
    assert await c.is_reachable_from_iran("dictform.example") is True


@pytest.mark.asyncio
async def test_http_error_returns_none_silently(monkeypatch):
    class _RaisingClient:
        def __init__(self, *_a, **_kw): pass

        async def __aenter__(self): return self

        async def __aexit__(self, *exc): return False

        async def get(self, *_a, **_kw):
            raise RuntimeError("network down")

    monkeypatch.setattr("ping_luma.ooni.httpx.AsyncClient", _RaisingClient)
    c = OoniClient()
    assert await c.is_reachable_from_iran("any.example") is None


# --- caching ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_per_host_cache_within_ttl(monkeypatch):
    payload = {"result": [{
        "ok_count": 90, "anomaly_count": 0, "confirmed_count": 0, "measurement_count": 100,
    }]}
    counter = {"n": 0}
    _client_with(payload, monkeypatch, count=counter)

    c = OoniClient(ttl_s=300)
    await c.is_reachable_from_iran("h1.example")
    await c.is_reachable_from_iran("h1.example")
    assert counter["n"] == 1, "second call within TTL should hit cache"
    await c.is_reachable_from_iran("h2.example")  # different host bypasses cache
    assert counter["n"] == 2


# --- disabled short-circuit -------------------------------------------------

@pytest.mark.asyncio
async def test_disabled_skips_network(monkeypatch):
    class _ShouldNotCall:
        def __init__(self, *_a, **_kw):
            raise AssertionError("OONI must not hit the network when disabled")

    monkeypatch.setattr("ping_luma.ooni.httpx.AsyncClient", _ShouldNotCall)
    c = OoniClient(enabled=False)
    assert await c.is_reachable_from_iran("any.example") is None
