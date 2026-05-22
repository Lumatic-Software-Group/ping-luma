from __future__ import annotations

from unittest import mock

from ping_luma.infrastructure import usage_log


def test_http_base_url() -> None:
    assert usage_log._http_base_url("libsql://abc-org.turso.io") == "https://abc-org.turso.io"
    assert usage_log._http_base_url("https://xyz.turso.io/") == "https://xyz.turso.io"


def _ok_results(n: int) -> dict:
    return {"results": [{"type": "ok"} for _ in range(n)]}


def test_submit_noop_when_unconfigured() -> None:
    with mock.patch.object(usage_log.config, "TURSO_DATABASE_URL", None):
        with mock.patch.object(usage_log.config, "TURSO_AUTH_TOKEN", "t"):
            with mock.patch("ping_luma.infrastructure.usage_log.httpx.post") as post:
                usage_log.submit(1, "start")
            post.assert_not_called()
    with mock.patch.object(usage_log.config, "TURSO_DATABASE_URL", "u"):
        with mock.patch.object(usage_log.config, "TURSO_AUTH_TOKEN", None):
            with mock.patch("ping_luma.infrastructure.usage_log.httpx.post") as post:
                usage_log.submit(1, "start")
            post.assert_not_called()


def test_ensure_schema_runs_create_if_not_exists_only() -> None:
    mock_resp = mock.MagicMock()
    mock_resp.raise_for_status = mock.MagicMock()
    mock_resp.json.return_value = _ok_results(3)
    with mock.patch.object(usage_log, "_usage_event_needs_rebuild", return_value=False):
        with mock.patch.object(usage_log, "_actor_needs_username_column", return_value=False):
            with mock.patch.object(usage_log.config, "TURSO_DATABASE_URL", "libsql://db.example.com"):
                with mock.patch.object(usage_log.config, "TURSO_AUTH_TOKEN", "tok"):
                    with mock.patch("ping_luma.infrastructure.usage_log.httpx.post", return_value=mock_resp) as post:
                        usage_log.ensure_schema()
    assert post.call_count == 1
    _, kwargs = post.call_args
    reqs = kwargs["json"]["requests"]
    assert len(reqs) == 3
    assert reqs[0]["stmt"]["sql"].startswith("CREATE TABLE IF NOT EXISTS usage_actor")
    assert reqs[1]["stmt"]["sql"].startswith("CREATE TABLE IF NOT EXISTS usage_event")
    assert reqs[2]["type"] == "close"


def test_usage_event_needs_rebuild() -> None:
    with mock.patch.object(
            usage_log,
            "_fetch_sqlite_master_ddl",
            return_value="CREATE TABLE usage_event (id INTEGER, user_id INTEGER)",
    ):
        assert usage_log._usage_event_needs_rebuild() is True
    with mock.patch.object(
            usage_log,
            "_fetch_sqlite_master_ddl",
            return_value="CREATE TABLE usage_event (user_no INTEGER NOT NULL)",
    ):
        assert usage_log._usage_event_needs_rebuild() is False
    with mock.patch.object(usage_log, "_fetch_sqlite_master_ddl", return_value=None):
        assert usage_log._usage_event_needs_rebuild() is False


def test_ensure_schema_drops_legacy_then_creates() -> None:
    responses = []
    for _ in range(2):
        m = mock.MagicMock()
        m.raise_for_status = mock.MagicMock()
        m.json.return_value = _ok_results(3)
        responses.append(m)
    with mock.patch.object(usage_log, "_usage_event_needs_rebuild", return_value=True):
        with mock.patch.object(usage_log, "_actor_needs_username_column", return_value=False):
            with mock.patch.object(usage_log.config, "TURSO_DATABASE_URL", "libsql://db.example.com"):
                with mock.patch.object(usage_log.config, "TURSO_AUTH_TOKEN", "tok"):
                    with mock.patch("ping_luma.infrastructure.usage_log.httpx.post", side_effect=responses) as post:
                        usage_log.ensure_schema()
    assert post.call_count == 2
    drop_req = post.call_args_list[0][1]["json"]["requests"]
    assert "DROP TABLE" in drop_req[0]["stmt"]["sql"]
    create_req = post.call_args_list[1][1]["json"]["requests"]
    assert create_req[0]["stmt"]["sql"].startswith("CREATE TABLE IF NOT EXISTS usage_actor")


@mock.patch.object(usage_log.config, "TURSO_DATABASE_URL", "libsql://db.example.com")
@mock.patch.object(usage_log.config, "TURSO_AUTH_TOKEN", "tok")
def test_submit_inserts_only_no_ddl() -> None:
    mock_resp = mock.MagicMock()
    mock_resp.raise_for_status = mock.MagicMock()
    mock_resp.json.return_value = _ok_results(3)
    with mock.patch("ping_luma.infrastructure.usage_log.httpx.post", return_value=mock_resp) as post:
        usage_log.submit(8596044462, "start", "d1")
    _, kwargs = post.call_args
    reqs = kwargs["json"]["requests"]
    assert len(reqs) == 3
    assert "CREATE TABLE" not in reqs[0]["stmt"]["sql"]
    assert "ON CONFLICT" in reqs[0]["stmt"]["sql"]
    assert reqs[0]["stmt"]["args"][0] == {"type": "integer", "value": "8596044462"}
    assert reqs[0]["stmt"]["args"][1] == {"type": "null"}
    ins = reqs[1]["stmt"]
    assert "INSERT INTO usage_event" in ins["sql"]
    assert ins["args"][2] == {"type": "integer", "value": "8596044462"}
    assert reqs[2]["type"] == "close"


@mock.patch.object(usage_log.config, "TURSO_DATABASE_URL", "libsql://db.example.com")
@mock.patch.object(usage_log.config, "TURSO_AUTH_TOKEN", "tok")
def test_submit_null_detail() -> None:
    mock_resp = mock.MagicMock()
    mock_resp.raise_for_status = mock.MagicMock()
    mock_resp.json.return_value = _ok_results(3)
    with mock.patch("ping_luma.infrastructure.usage_log.httpx.post", return_value=mock_resp) as post:
        usage_log.submit(1, "start", None)
    ins = post.call_args[1]["json"]["requests"][1]["stmt"]
    assert ins["args"][1] == {"type": "null"}


def test_submit_passes_normalized_username() -> None:
    mock_resp = mock.MagicMock()
    mock_resp.raise_for_status = mock.MagicMock()
    mock_resp.json.return_value = _ok_results(3)
    with mock.patch.object(usage_log.config, "TURSO_DATABASE_URL", "libsql://db.example.com"):
        with mock.patch.object(usage_log.config, "TURSO_AUTH_TOKEN", "tok"):
            with mock.patch("ping_luma.infrastructure.usage_log.httpx.post", return_value=mock_resp) as post:
                usage_log.submit(1, "start", telegram_username="  @MyBrand  ")
    args = post.call_args[1]["json"]["requests"][0]["stmt"]["args"]
    assert args[1] == {"type": "text", "value": "mybrand"}


def test_normalize_username() -> None:
    assert usage_log._normalize_username("@AbC") == "abc"
    assert usage_log._normalize_username(None) is None
    assert usage_log._normalize_username("  ") is None


def test_configured() -> None:
    with mock.patch.object(usage_log.config, "TURSO_DATABASE_URL", "u"):
        with mock.patch.object(usage_log.config, "TURSO_AUTH_TOKEN", "t"):
            assert usage_log.configured() is True


def test_webapp_payload_detail() -> None:
    s = usage_log.webapp_payload_detail({
        "kind": "pingluma_result",
        "ts": 1,
        "country": "IR",
        "results": [
            {"id": "bale", "chat_ok": True},
            {"id": "gap", "chat_ok": False},
        ],
    })
    assert '"cc":"IR"' in s
    assert '"n_ok":1' in s
    assert '"n_fail":1' in s
    assert '"n":2' in s
