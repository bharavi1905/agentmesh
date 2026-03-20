import logging
import time
from typing import Any

import requests

from utils.config import NSE_BASE_URL, NSE_ANNOUNCEMENTS_URL

logger = logging.getLogger(__name__)

NSE_HOME = NSE_BASE_URL

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


def _parse_announcement(raw: dict[str, Any]) -> dict[str, str]:
    symbol = raw.get("symbol") or raw.get("sm_isin") or ""
    subject = raw.get("subject") or raw.get("desc") or ""
    date = raw.get("exchdisstime") or raw.get("bm_timestamp") or raw.get("an_dt") or ""
    description = raw.get("body") or raw.get("attchmnt") or subject
    # NSE announcements link to the attachment or the announcements page
    attach = raw.get("attchmnt") or ""
    if attach and attach.startswith("http"):
        url = attach
    elif attach:
        url = f"{NSE_HOME}/{attach.lstrip('/')}"
    else:
        url = NSE_ANNOUNCEMENTS_URL

    return {
        "symbol": symbol,
        "subject": subject,
        "date": date,
        "description": description,
        "url": url,
    }


def fetch_nse_announcements() -> list[dict[str, str]]:
    """Fetch NSE corporate announcements for equities.

    Returns a list of dicts with keys: symbol, subject, date, description, url.
    Retries up to 3 times with exponential backoff on failure.
    """
    last_exc: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("fetch_nse_announcements: attempt %d/%d", attempt, MAX_RETRIES)
        session = _make_session()

        try:
            # Step 1 — hit the home page to establish cookies
            home_resp = session.get(NSE_HOME, timeout=15)
            logger.debug(
                "Home page status: %d, cookies: %s",
                home_resp.status_code,
                list(session.cookies.keys()),
            )

            # Brief pause — mimics a real browser
            time.sleep(1)

            # Step 2 — hit the API endpoint
            api_resp = session.get(NSE_ANNOUNCEMENTS_URL, timeout=15)
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

            # The endpoint returns a list directly, or sometimes {"data": [...]}
            if isinstance(data, list):
                records = data
            elif isinstance(data, dict):
                records = data.get("data") or data.get("announcements") or []
            else:
                records = []

            logger.info(
                "fetch_nse_announcements: received %d records", len(records)
            )
            return [_parse_announcement(r) for r in records]

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
    results = fetch_nse_announcements()
    print(f"\nTotal announcements fetched: {len(results)}\n")
    for r in results[:3]:
        print(r)
