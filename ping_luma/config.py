import os
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()


def _int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


def _float(key: str, default: float) -> float:
    return float(os.getenv(key, str(default)))


def _bool(key: str, default: bool) -> bool:
    return os.getenv(key, str(default)).lower() in ("1", "true", "yes")


def _list_int(key: str) -> List[int]:
    return [int(x) for x in os.getenv(key, "").split(",") if x.strip()]


# bot username: @ping_luma_bot
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

# telegram api
BASE_URL: str = os.getenv("BASE_URL", "https://api.telegram.org/bot")

PROXY_URL: Optional[str] = os.getenv("PROXY_URL", "") or None
CONNECT_TIMEOUT: float = _float("CONNECT_TIMEOUT", 30)
READ_TIMEOUT: float = _float("READ_TIMEOUT", 30)
WRITE_TIMEOUT: float = _float("WRITE_TIMEOUT", 30)

# polling True  = discard queued updates on startup so code changes take effect
#         immediately and users never see responses to old commands.
# polling False = process all queued updates.
# override via .env:  DROP_PENDING=false
DROP_PENDING: bool = _bool("DROP_PENDING", True)

# rate limit min seconds between scans per user.
SCAN_COOLDOWN: int = _int("SCAN_COOLDOWN", 30)

# background broadcast Interval in minutes between automatic global-status checks (0 = disabled).
AUTO_CHECK_INTERVAL: int = _int("AUTO_CHECK_INTERVAL", 30)
ALERT_CHAT_IDS: List[int] = _list_int("ALERT_CHAT_IDS")
