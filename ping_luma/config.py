"""Environment-driven runtime configuration."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


def _float(key: str, default: float) -> float:
    return float(os.getenv(key, str(default)))


def _bool(key: str, default: bool) -> bool:
    return os.getenv(key, str(default)).lower() in ("1", "true", "yes")


# Bot username: @ping_luma_bot
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

# telegram api
BASE_URL: str = os.getenv("BASE_URL", "https://api.telegram.org/bot")

PROXY_URL: str | None = os.getenv("PROXY_URL", "") or None
CONNECT_TIMEOUT: float = _float("CONNECT_TIMEOUT", 30)
READ_TIMEOUT: float = _float("READ_TIMEOUT", 30)
WRITE_TIMEOUT: float = _float("WRITE_TIMEOUT", 30)

# WebApp URL — must be HTTPS and reachable from the user's Telegram client.
# This is the single source of truth for "your network" results.
WEBAPP_URL: str = os.getenv("WEBAPP_URL", "https://pingluma.app")

# ─── Iran reference: HTTP override (optional) ─────────────────────────────
IRAN_REFERENCE_URL: str | None = os.getenv("IRAN_REFERENCE_URL", "") or None
IRAN_REFERENCE_TOKEN: str | None = (
        os.getenv("IRAN_REFERENCE_TOKEN", "") or None
)
IRAN_REFERENCE_TIMEOUT_S: float = _float("IRAN_REFERENCE_TIMEOUT_S", 6.0)

# ─── Iran reference: ASN classifier ───────────────────────────────────────
ASN_MAP_PATH: str = os.getenv("ASN_MAP_PATH", "ping_luma/asn_map.json")

# ─── Iran reference: OONI (historical censorship data) ────────────────────
OONI_ENABLED: bool = _bool("OONI_ENABLED", True)
OONI_LOOKBACK_DAYS: int = _int("OONI_LOOKBACK_DAYS", 7)
OONI_TTL_S: int = _int("OONI_TTL_S", 86400)
OONI_TIMEOUT_S: float = _float("OONI_TIMEOUT_S", 15.0)
OONI_SUCCESS_THRESHOLD: float = _float("OONI_SUCCESS_THRESHOLD", 0.7)
OONI_BLOCKED_THRESHOLD: float = _float("OONI_BLOCKED_THRESHOLD", 0.5)
OONI_MIN_MEASUREMENTS: int = _int("OONI_MIN_MEASUREMENTS", 3)

# ─── Iran reference: Crowdsource (live samples from real users) ───────────
CROWD_ENABLED: bool = _bool("CROWD_ENABLED", True)
CROWD_COUNTRY: str = os.getenv("CROWD_COUNTRY", "IR")
CROWD_MAX_AGE_S: int = _int("CROWD_MAX_AGE_S", 1200)
CROWD_MAX_PER_MESSENGER: int = _int("CROWD_MAX_PER_MESSENGER", 30)
CROWD_DEDUP_WINDOW_S: int = _int("CROWD_DEDUP_WINDOW_S", 1200)
CROWD_MIN_SAMPLES: int = _int("CROWD_MIN_SAMPLES", 3)
CROWD_SUCCESS_THRESHOLD: float = _float("CROWD_SUCCESS_THRESHOLD", 0.7)
CROWD_BLOCKED_THRESHOLD: float = _float("CROWD_BLOCKED_THRESHOLD", 0.3)

# Cache TTL for the merged Iran-reference snapshot. Also used as the
# cadence of the background refresh loop in ping_luma.bot. 21600s = 6h.
IRAN_REFERENCE_TTL_S: int = _int("IRAN_REFERENCE_TTL_S", 21600)

# True  = discard queued updates on startup (recommended during development)
# False = process all queued updates
DROP_PENDING: bool = _bool("DROP_PENDING", True)
