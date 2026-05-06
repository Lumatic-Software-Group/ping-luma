from __future__ import annotations

import json
import logging

import httpx

from ping_luma import config

log = logging.getLogger(__name__)

_CREATE_ACTOR_SQL = """
CREATE TABLE IF NOT EXISTS usage_actor (
    user_no INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id INTEGER NOT NULL UNIQUE,
    telegram_username TEXT
)
""".strip()

_CREATE_EVENT_SQL = """
CREATE TABLE IF NOT EXISTS usage_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    user_no INTEGER NOT NULL,
    action TEXT NOT NULL,
    detail TEXT
)
""".strip()

_UPSERT_ACTOR_SQL = """
INSERT INTO usage_actor (telegram_user_id, telegram_username) VALUES (?, ?)
ON CONFLICT(telegram_user_id) DO UPDATE SET
    telegram_username = COALESCE(excluded.telegram_username, usage_actor.telegram_username)
""".strip()

_INSERT_EVENT_SQL = """
INSERT INTO usage_event (user_no, action, detail)
SELECT a.user_no, ?, ? FROM usage_actor a WHERE a.telegram_user_id = ? LIMIT 1
""".strip()


def _http_base_url(database_url: str) -> str:
    u = database_url.strip().rstrip("/")
    if u.startswith("libsql://"):
        return "https://" + u[len("libsql://") :]
    if u.startswith("https://"):
        return u
    return u


def _arg_int(n: int) -> dict:
    return {"type": "integer", "value": str(int(n))}


def _arg_text(s: str) -> dict:
    return {"type": "text", "value": s}


def _arg_null() -> dict:
    return {"type": "null"}


def _normalize_username(raw: str | None) -> str | None:
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip().lstrip("@")[:64]
    return s.lower() if s else None


def configured() -> bool:
    return bool(config.TURSO_DATABASE_URL and config.TURSO_AUTH_TOKEN)


def _post_pipeline(body: dict) -> dict | None:
    if not configured():
        return None
    base = _http_base_url(config.TURSO_DATABASE_URL or "")
    try:
        r = httpx.post(
            f"{base}/v2/pipeline",
            headers={
                "Authorization": f"Bearer {config.TURSO_AUTH_TOKEN}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=25.0,
        )
        r.raise_for_status()
        data = r.json()
        for item in data.get("results", []):
            if item.get("type") != "ok":
                log.warning("usage log pipeline rejected: %s", item)
                return None
        return data
    except httpx.HTTPError as exc:
        log.warning("usage log HTTP error: %s", exc)
    except Exception as exc:
        log.warning("usage log request failed: %s", exc)
    return None


def _pipeline(execute_steps: list[dict]) -> bool:
    body = {"requests": [*execute_steps, {"type": "close"}]}
    return _post_pipeline(body) is not None


def _fetch_sqlite_master_ddl(table: str) -> str | None:
    data = _post_pipeline(
        {
            "requests": [
                {
                    "type": "execute",
                    "stmt": {
                        "sql": (
                            "SELECT sql FROM sqlite_master "
                            "WHERE type='table' AND name=?"
                        ),
                        "args": [_arg_text(table)],
                    },
                },
                {"type": "close"},
            ],
        },
    )
    if not data:
        return None
    for item in data.get("results", []):
        if item.get("type") != "ok":
            continue
        resp = item.get("response", {})
        if resp.get("type") != "execute":
            continue
        rows = resp.get("result", {}).get("rows", [])
        if not rows or not rows[0]:
            return None
        cell = rows[0][0]
        if isinstance(cell, dict) and cell.get("type") == "text":
            return cell.get("value")
        return None
    return None


def _actor_needs_username_column() -> bool:
    ddl = _fetch_sqlite_master_ddl("usage_actor")
    if not ddl:
        return False
    return "telegram_username" not in ddl


def _usage_event_needs_rebuild() -> bool:
    ddl = _fetch_sqlite_master_ddl("usage_event")
    if not ddl:
        return False
    return "user_no" not in ddl


def ensure_schema() -> None:
    """Ensure tables exist. Migrates away from legacy ``usage_event`` (``user_id`` column)."""
    if not configured():
        return
    if _usage_event_needs_rebuild():
        log.warning(
            "usage_event table uses a legacy schema; replacing usage_event and usage_actor"
        )
        _pipeline(
            [
                {"type": "execute", "stmt": {"sql": "DROP TABLE IF EXISTS usage_event"}},
                {"type": "execute", "stmt": {"sql": "DROP TABLE IF EXISTS usage_actor"}},
            ],
        )
    ok = _pipeline(
        [
            {"type": "execute", "stmt": {"sql": _CREATE_ACTOR_SQL}},
            {"type": "execute", "stmt": {"sql": _CREATE_EVENT_SQL}},
        ],
    )
    if ok:
        if _actor_needs_username_column():
            log.info("usage_actor: adding telegram_username column for existing database")
            _pipeline(
                [
                    {
                        "type": "execute",
                        "stmt": {
                            "sql": (
                                "ALTER TABLE usage_actor "
                                "ADD COLUMN telegram_username TEXT"
                            ),
                        },
                    },
                ],
            )
        log.info(
            "usage DB tables ensured "
            "(usage_actor.telegram_user_id, telegram_username, usage_event)"
        )
    else:
        log.warning("usage DB schema could not be verified; events may fail until this succeeds")


def submit(
        user_id: int | str,
        action: str,
        detail: str | None = None,
        telegram_username: str | None = None,
) -> None:
    if not configured():
        return
    tg = int(user_id) if isinstance(user_id, str) and user_id.isdigit() else int(user_id)
    detail_sql: dict = (
        _arg_text(detail[:16000]) if (detail and detail.strip()) else _arg_null()
    )
    uname = _normalize_username(telegram_username)
    user_sql = _arg_text(uname) if uname else _arg_null()
    _pipeline(
        [
            {
                "type": "execute",
                "stmt": {
                    "sql": _UPSERT_ACTOR_SQL,
                    "args": [_arg_int(tg), user_sql],
                },
            },
            {
                "type": "execute",
                "stmt": {
                    "sql": _INSERT_EVENT_SQL,
                    "args": [
                        _arg_text(action[:2000]),
                        detail_sql,
                        _arg_int(tg),
                    ],
                },
            },
        ],
    )


def webapp_payload_detail(payload: dict) -> str:
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    n_ok = sum(1 for r in results if isinstance(r, dict) and r.get("chat_ok") is True)
    n_fail = sum(
        1 for r in results
        if isinstance(r, dict) and r.get("chat_ok") is False
    )
    blob = {
        "ts": payload.get("ts"),
        "cc": payload.get("country"),
        "n_ok": n_ok,
        "n_fail": n_fail,
        "n": len(results),
    }
    return json.dumps(blob, separators=(",", ":"), ensure_ascii=False)
