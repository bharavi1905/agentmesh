import logging
import time

import requests

logger = logging.getLogger(__name__)

NSE_HOME = "https://www.nseindia.com"
NSE_BULK_DEALS_URL = (
    "https://www.nseindia.com/api/snapshot-capital-market-largedeal?index=bulk_deals"
)
NSE_BLOCK_DEALS_URL = (
    "https://www.nseindia.com/api/snapshot-capital-market-largedeal?index=block_deals"
)

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


def _parse_deal(raw: dict, deal_type: str) -> dict:
    symbol = raw.get("symbol") or ""
    client = raw.get("clientName") or ""
    buy_sell = (raw.get("buySell") or "").upper()  # "BUY" or "SELL"
    try:
        quantity = float(raw.get("qty") or 0)
    except (ValueError, TypeError):
        quantity = 0.0
    try:
        price = float(raw.get("watp") or 0)  # weighted average trade price
    except (ValueError, TypeError):
        price = 0.0
    value_cr = round(quantity * price / 1_00_00_000, 2)

    return {
        "symbol": symbol,
        "client": client,
        "deal_type": deal_type,
        "buy_sell": buy_sell,
        "quantity": int(quantity),
        "price": price,
        "value_cr": value_cr,
    }


def _fetch_deals(url: str, deal_type: str, response_key: str) -> list[dict]:
    last_exc: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("fetch_%s_deals: attempt %d/%d", deal_type, attempt, MAX_RETRIES)
        session = _make_session()

        try:
            home_resp = session.get(NSE_HOME, timeout=15)
            logger.debug(
                "Home page status: %d, cookies: %s",
                home_resp.status_code,
                list(session.cookies.keys()),
            )

            time.sleep(1)

            api_resp = session.get(url, timeout=15)
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

            if isinstance(data, dict):
                logger.debug("fetch_%s_deals: response keys: %s", deal_type, list(data.keys()))

            if isinstance(data, list):
                records = data
            elif isinstance(data, dict):
                records = data.get(response_key) or []
            else:
                records = []

            if not records:
                logger.debug(
                    "fetch_%s_deals: empty result — NSE only publishes %s deals "
                    "after market close (~6–7pm IST); this is normal during market hours",
                    deal_type, deal_type,
                )
                return []

            logger.info("fetch_%s_deals: received %d records", deal_type, len(records))
            return [_parse_deal(r, deal_type) for r in records]

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


def fetch_bulk_deals() -> list[dict]:
    """Fetch NSE bulk deals for today.

    Returns a list of dicts with keys: symbol, client, deal_type, quantity, price, value_cr.
    Only populated after market close (~6–7pm IST). Returns [] during market hours.
    """
    return _fetch_deals(NSE_BULK_DEALS_URL, "bulk", "BULK_DEALS_DATA")


def fetch_block_deals() -> list[dict]:
    """Fetch NSE block deals for today.

    Returns a list of dicts with keys: symbol, client, deal_type, quantity, price, value_cr.
    Only populated after market close (~6–7pm IST). Returns [] during market hours.
    """
    return _fetch_deals(NSE_BLOCK_DEALS_URL, "block", "BLOCK_DEALS_DATA")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    print("\n--- Bulk Deals ---")
    bulk = fetch_bulk_deals()
    print(f"Total: {len(bulk)}")
    for d in bulk[:3]:
        print(d)

    print("\n--- Block Deals ---")
    block = fetch_block_deals()
    print(f"Total: {len(block)}")
    for d in block[:3]:
        print(d)
