"""
ping_luma/config.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
All runtime configuration.  Values are read from environment variables
so the same image works in every environment (local / CI / prod).
Copy .env.example → .env and fill in your values.

PROXY_URL quick-start
  Option A — System VPN active, leave PROXY_URL empty
  Option B — SSH tunnel / Shadowsocks / Outline
              PROXY_URL=socks5://127.0.0.1:1080
  Option C — HTTP proxy (Charles, Squid …)
              PROXY_URL=http://127.0.0.1:8888
"""

import os
from dotenv import load_dotenv
from typing import List, Optional

load_dotenv()

def _int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


def _float(key: str, default: float) -> float:
    return float(os.getenv(key, str(default)))


def _list_int(key: str) -> List[int]:
    return [int(x) for x in os.getenv(key, "").split(",") if x.strip()]


# ── Bot ───────────────────────────────────────────────────────────────────────
# Bale:     @BotFather_bot → /newbot → copy token
# Telegram: @BotFather     → /newbot → copy token
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

# Bale Bot API  → "https://tapi.bale.ai/bot"
# Telegram API  → "https://api.telegram.org/bot"
BASE_URL: str = os.getenv("BASE_URL", "https://api.telegram.org/bot")

# ── Network ───────────────────────────────────────────────────────────────────
PROXY_URL: Optional[str] = os.getenv("PROXY_URL", "") or None
CONNECT_TIMEOUT: float   = _float("CONNECT_TIMEOUT", 30)
READ_TIMEOUT: float      = _float("READ_TIMEOUT",    30)
WRITE_TIMEOUT: float     = _float("WRITE_TIMEOUT",   30)

# ── Cache ─────────────────────────────────────────────────────────────────────
# Seconds before a cached check result is considered stale.
# /status will auto-rerun the check when the entry has expired.
CACHE_TTL: int = _int("CACHE_TTL", 300)   # 5 minutes default

# ── Auto-broadcast ────────────────────────────────────────────────────────────
# Set to 0 to disable background probing.
AUTO_CHECK_INTERVAL: int    = _int("AUTO_CHECK_INTERVAL", 15)   # minutes
ALERT_CHAT_IDS: List[int]   = _list_int("ALERT_CHAT_IDS")