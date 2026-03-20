import logging
import time

import requests

from utils.config import NSE_BASE_URL, NSE_FII_DII_URL

logger = logging.getLogger(__name__)

NSE_HOME = NSE_BASE_URL
FII_DII_URL = NSE_FII_DII_URL

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


def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def _parse_cr(value) -> float:
    """Parse a string or number value into a crores float."""
    try:
        if isinstance(value, (int, float)):
            return round(float(value), 2)
        if isinstance(value, str):
            return round(float(value.replace(",", "").strip()), 2)
    except (ValueError, TypeError):
        pass
    return 0.0


def _build_result(fii_net_cr: float, dii_net_cr: float, date_str: str) -> dict:
    if fii_net_cr > 500:
        sentiment = "bullish"
        context = (
            f"FII net bought ₹{abs(fii_net_cr):,.0f} Cr today "
            "— institutional buying supports bullish signals"
        )
    elif fii_net_cr < -500:
        sentiment = "bearish"
        context = (
            f"FII net sold ₹{abs(fii_net_cr):,.0f} Cr today "
            "— institutional selling reduces confidence in bullish alerts"
        )
    else:
        sentiment = "neutral"
        context = (
            f"FII flows neutral at ₹{fii_net_cr:+,.0f} Cr "
            "— no strong institutional conviction today"
        )

    return {
        "date": date_str,
        "fii_net_cr": fii_net_cr,
        "dii_net_cr": dii_net_cr,
        "sentiment": sentiment,
        "context": context,
    }


def fetch_fii_dii_flows() -> dict:
    """Fetch today's FII and DII net buy/sell flows from NSE.

    Returns dict with:
    - date: str
    - fii_net_cr: float (positive=buying, negative=selling, in crores)
    - dii_net_cr: float
    - sentiment: "bullish" | "bearish" | "neutral"
    - context: str — one sentence summary for scorer

    Returns {} on any failure — scorer treats missing data as neutral.
    """
    session = _make_session()
    try:
        session.get(NSE_HOME, timeout=15)
        time.sleep(1)
    except Exception as exc:
        logger.warning("FII/DII session setup failed: %s", exc)
        return {}

    try:
        resp = session.get(FII_DII_URL, timeout=15)
        resp.raise_for_status()
        records = resp.json()  # list of dicts: [{category, date, buyValue, sellValue, netValue}]

        if not isinstance(records, list) or not records:
            logger.warning("FII/DII: unexpected response format")
            return {}

        fii_net_cr = 0.0
        dii_net_cr = 0.0
        date_str = ""

        for rec in records:
            category = (rec.get("category") or "").upper()
            net = _parse_cr(rec.get("netValue", 0))
            date_str = date_str or rec.get("date", "")

            if "FII" in category or "FPI" in category:
                fii_net_cr = net
            elif "DII" in category:
                dii_net_cr = net

        result = _build_result(fii_net_cr, dii_net_cr, date_str)
        logger.info(
            "FII/DII [%s]: fii=₹%.0f Cr, dii=₹%.0f Cr, sentiment=%s",
            date_str, fii_net_cr, dii_net_cr, result["sentiment"],
        )
        return result

    except Exception as exc:
        logger.error("FII/DII fetch failed: %s: %s", type(exc).__name__, exc)
        return {}


if __name__ == "__main__":
    import json
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    print("\n--- FII/DII Flows ---")
    result = fetch_fii_dii_flows()
    if result:
        print(json.dumps(result, indent=2))
    else:
        print("No data returned")
