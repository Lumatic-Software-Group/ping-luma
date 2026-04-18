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


# Get your token from @BotFather on Telegram
# Bot username: @ping_luma_bot
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

# Telegram API
BASE_URL: str = os.getenv("BASE_URL", "https://api.telegram.org/bot")

PROXY_URL: Optional[str] = os.getenv("PROXY_URL", "") or None
CONNECT_TIMEOUT: float = _float("CONNECT_TIMEOUT", 30)
READ_TIMEOUT: float = _float("READ_TIMEOUT", 30)
WRITE_TIMEOUT: float = _float("WRITE_TIMEOUT", 30)

# Seconds before a cached scan is considered stale.
# /status will auto-rerun when the entry has expired.
CACHE_TTL: int = _int("CACHE_TTL", 300)  # 5 minutes

# Minimum seconds between scans per user (prevents abuse).
SCAN_COOLDOWN: int = _int("SCAN_COOLDOWN", 30)

# Minutes between background global probes (0 = disabled).
AUTO_CHECK_INTERVAL: int = _int("AUTO_CHECK_INTERVAL", 30)
ALERT_CHAT_IDS: List[int] = _list_int("ALERT_CHAT_IDS")
