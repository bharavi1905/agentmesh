import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (two levels up from this file)
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            f"Check your .env file at {_env_path}"
        )
    return value


def _bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).strip().lower() in ("1", "true", "yes")


def _int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


# --- Exported settings ---

TELEGRAM_BOT_TOKEN: str = _require("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID: str = _require("TELEGRAM_CHAT_ID")
DRY_RUN: bool = _bool("DRY_RUN", default=True)
ALERT_SCORE_THRESHOLD: int = _int("ALERT_SCORE_THRESHOLD", default=7)

# ─── NSE ────────────────────────────────────────────────
NSE_BASE_URL           = "https://www.nseindia.com"
NSE_HOME               = NSE_BASE_URL
NSE_ANNOUNCEMENTS_URL  = f"{NSE_BASE_URL}/api/corporate-announcements?index=equities"
NSE_BULK_DEALS_URL     = f"{NSE_BASE_URL}/api/snapshot-capital-market-largedeal?index=bulk_deals"
NSE_BLOCK_DEALS_URL    = f"{NSE_BASE_URL}/api/snapshot-capital-market-largedeal?index=block_deals"
NSE_EVENT_CALENDAR_URL = f"{NSE_BASE_URL}/api/event-calendar"
NSE_FII_DII_URL        = f"{NSE_BASE_URL}/api/fiidiiTradeReact"
NSE_HOLIDAY_MASTER_URL = f"{NSE_BASE_URL}/api/holiday-master?type=trading"

# ─── NSE page URLs (for alert source links) ─────────────
NSE_BULK_DEALS_PAGE    = f"{NSE_BASE_URL}/market-data/bulk-deals"
NSE_BLOCK_DEALS_PAGE   = f"{NSE_BASE_URL}/market-data/block-deals"
NSE_ANNOUNCEMENTS_PAGE = f"{NSE_BASE_URL}/companies-listing/corporate-filings-announcements"

# ─── RSS feeds ──────────────────────────────────────────
RBI_PRESS_RSS_URL         = "https://www.rbi.org.in/pressreleases_rss.xml"
RBI_NOTIFICATIONS_RSS_URL = "https://www.rbi.org.in/notifications_rss.xml"
SEBI_RSS_URL              = "https://www.sebi.gov.in/sebirss.xml"

# ─── NSE equity list ────────────────────────────────────
NSE_EQUITY_LIST_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"

# ─── Screener.in ────────────────────────────────────────
SCREENER_BASE = "https://www.screener.in"

# ─── Telegram ───────────────────────────────────────────
TELEGRAM_API_BASE = "https://api.telegram.org"
