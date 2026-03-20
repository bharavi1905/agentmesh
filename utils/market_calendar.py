import logging
import time
from datetime import date, datetime

import requests

from utils.config import NSE_BASE_URL, NSE_HOLIDAY_MASTER_URL

logger = logging.getLogger(__name__)

NSE_HOME = NSE_BASE_URL
NSE_HOLIDAY_URL = NSE_HOLIDAY_MASTER_URL

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://www.nseindia.com",
    "Connection": "keep-alive",
    "DNT": "1",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

# year -> set of holiday dates
_holiday_cache: dict[int, set[date]] = {}


def _fetch_holidays_for_year(year: int) -> set[date]:
    """Fetch NSE trading holidays for the given year. Returns empty set on failure."""
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        session.get(NSE_HOME, timeout=15)
        time.sleep(1)
        resp = session.get(NSE_HOLIDAY_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # Response shape: {"CM": [...], "FO": [...], ...}
        # CM = Capital Markets (equities)
        cm_holidays = data.get("CM") or []
        holidays: set[date] = set()

        for item in cm_holidays:
            raw_date = item.get("tradingDate") or item.get("date") or ""
            if not raw_date:
                continue
            parsed = _parse_nse_date(raw_date)
            if parsed and parsed.year == year:
                holidays.add(parsed)

        logger.info("Loaded %d NSE trading holidays for %d", len(holidays), year)
        return holidays

    except Exception as exc:
        logger.warning("Failed to fetch NSE holiday list: %s: %s", type(exc).__name__, exc)
        return set()


def _parse_nse_date(raw: str) -> date | None:
    """Parse NSE date formats like '19-Mar-2026' or '2026-03-19'."""
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def _get_holidays(year: int) -> set[date]:
    if year not in _holiday_cache:
        _holiday_cache[year] = _fetch_holidays_for_year(year)
    return _holiday_cache[year]


def is_market_holiday(check_date: date | None = None) -> bool:
    """Return True if the given date is an NSE trading holiday.

    Uses NSE holiday-master API. Caches result for the day.
    Falls back to False (assume market open) on any error.
    """
    if check_date is None:
        check_date = date.today()
    holidays = _get_holidays(check_date.year)
    return check_date in holidays


def is_market_open_today() -> bool:
    """Return True if today is a trading day (not holiday, not weekend)."""
    today = date.today()
    if today.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return not is_market_holiday(today)


if __name__ == "__main__":
    import json
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    today = date.today()
    holiday = is_market_holiday()
    print(f"\nToday ({today}): {'a HOLIDAY' if holiday else 'a trading day'}")
    print(f"Market open today: {is_market_open_today()}")

    # Show all loaded holidays so we can verify
    holidays = _get_holidays(today.year)
    print(f"\nAll NSE holidays for {today.year} ({len(holidays)} total):")
    for h in sorted(holidays):
        print(f"  {h}")
