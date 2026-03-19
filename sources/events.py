import logging
import time
import datetime

import requests

logger = logging.getLogger(__name__)

NSE_HOME = "https://www.nseindia.com"
NSE_EVENT_CALENDAR_URL = "https://www.nseindia.com/api/event-calendar"

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

MAX_RETRIES = 3
BACKOFF_SECONDS = [2, 4, 8]


def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def _parse_event_date(raw_date: str) -> datetime.date | None:
    """Parse NSE date strings like '19-Mar-2026' into a date object."""
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(raw_date.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def _parse_event(raw: dict) -> dict:
    symbol = raw.get("symbol") or raw.get("sm_symbol") or ""
    company = raw.get("company") or raw.get("sm_name") or ""
    event_type = raw.get("purpose") or raw.get("bm_purpose") or raw.get("type") or ""
    event_date_raw = (
        raw.get("date") or raw.get("bm_date") or raw.get("event_date") or ""
    )
    purpose = raw.get("description") or raw.get("bm_desc") or event_type
    attach = raw.get("attchmnt") or ""
    if attach and attach.startswith("http"):
        url = attach
    elif attach:
        url = f"{NSE_HOME}/{attach.lstrip('/')}"
    else:
        url = NSE_HOME

    return {
        "symbol": symbol,
        "company": company,
        "event_type": event_type,
        "event_date": event_date_raw,
        "_parsed_date": _parse_event_date(event_date_raw),
        "purpose": purpose,
        "url": url,
    }


def fetch_event_calendar() -> list[dict]:
    """Fetch NSE event calendar and return events within the next 7 days.

    Returns a list of dicts with keys: symbol, company, event_type,
    event_date, purpose, url. Returns [] on failure.
    """
    today = datetime.date.today()
    cutoff = today + datetime.timedelta(days=7)
    last_exc: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("fetch_event_calendar: attempt %d/%d", attempt, MAX_RETRIES)
        session = _make_session()

        try:
            home_resp = session.get(NSE_HOME, timeout=15)
            logger.debug(
                "Home page status: %d, cookies: %s",
                home_resp.status_code,
                list(session.cookies.keys()),
            )

            time.sleep(1)

            api_resp = session.get(NSE_EVENT_CALENDAR_URL, timeout=15)
            logger.info(
                "API response status: %d (attempt %d)", api_resp.status_code, attempt
            )

            if api_resp.status_code == 403:
                logger.warning(
                    "403 Forbidden on attempt %d — NSE may have rotated its bot check",
                    attempt,
                )
                raise requests.HTTPError("403 Forbidden", response=api_resp)

            api_resp.raise_for_status()

            data = api_resp.json()

            if isinstance(data, list):
                records = data
            elif isinstance(data, dict):
                records = data.get("data") or data.get("eventCalendar") or []
            else:
                records = []

            logger.info("fetch_event_calendar: received %d total records", len(records))

            events = []
            for r in records:
                parsed = _parse_event(r)
                d = parsed.pop("_parsed_date")
                if d is not None and today <= d <= cutoff:
                    events.append(parsed)

            logger.info(
                "fetch_event_calendar: %d events within next 7 days", len(events)
            )
            return events

        except Exception as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                wait = BACKOFF_SECONDS[attempt - 1]
                logger.warning(
                    "Attempt %d failed (%s: %s) — retrying in %ds",
                    attempt,
                    type(exc).__name__,
                    exc,
                    wait,
                )
                time.sleep(wait)
            else:
                logger.error(
                    "All %d attempts failed. Last error: %s: %s",
                    MAX_RETRIES,
                    type(exc).__name__,
                    exc,
                )

    return []


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    events = fetch_event_calendar()
    print(f"\nUpcoming events (next 7 days): {len(events)}")
    for e in events[:5]:
        print(f"  {e['event_date']} | {e['symbol']} | {e['event_type']} | {e['purpose'][:60]}")
