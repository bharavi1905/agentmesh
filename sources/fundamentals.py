import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from utils.config import SCREENER_BASE

logger = logging.getLogger(__name__)

SCREENER_COMPANY_URL = f"{SCREENER_BASE}/company"

# Module-level cache — avoids repeat searches within the same process
_slug_cache: dict[str, str] = {}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.screener.in",
}


def _find_screener_slug(symbol: str) -> str:
    """Find correct Screener.in slug for an NSE symbol.

    1. Try direct URL first — works for most symbols.
    2. If 404, query Screener.in autocomplete API.
    3. Cache result to avoid repeat lookups within the same process.

    Returns correct slug, or original symbol as fallback.
    """
    if symbol in _slug_cache:
        return _slug_cache[symbol]

    # Try direct consolidated URL first
    direct_url = f"{SCREENER_COMPANY_URL}/{symbol}/consolidated/"
    try:
        resp = requests.get(direct_url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            _slug_cache[symbol] = symbol
            return symbol
    except Exception:
        pass

    # Direct URL failed — search Screener autocomplete
    search_url = f"https://www.screener.in/api/company/search/?q={symbol}&auto=1"
    try:
        resp = requests.get(search_url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            results = resp.json()
            if results:
                # URL is like '/company/TEXRAIL/consolidated/'
                url_path = results[0].get("url", "")
                parts = url_path.strip("/").split("/")
                if len(parts) >= 2 and parts[0] == "company":
                    slug = parts[1]
                    logger.info(
                        "_find_screener_slug(%s): resolved to '%s' via search",
                        symbol,
                        slug,
                    )
                    _slug_cache[symbol] = slug
                    return slug
    except Exception as exc:
        logger.warning("_find_screener_slug(%s): search failed: %s", symbol, exc)

    # Fallback — use original symbol
    _slug_cache[symbol] = symbol
    return symbol


def fetch_fundamentals(ticker: str) -> dict:
    """Scrape key fundamentals for a stock from Screener.in.

    ticker: NSE symbol like "UNOMINDA" or "UNOMINDA.NS"
    Strips .NS / .BO suffix automatically.

    Returns dict with raw numbers. Returns {} on failure — scorer proceeds
    without fundamentals.
    """
    symbol = ticker.upper().replace(".NS", "").replace(".BO", "")
    slug = _find_screener_slug(symbol)
    url = f"{SCREENER_COMPANY_URL}/{slug}/consolidated/"

    try:
        for attempt in range(3):
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 429:
                wait = 2 ** attempt  # 1s, 2s, 4s backoff
                logger.warning(
                    "fetch_fundamentals(%s): HTTP 429, retrying in %ds", symbol, wait
                )
                time.sleep(wait)
                continue
            break

        # If consolidated not found, try standalone
        if resp.status_code == 404:
            url = f"{SCREENER_COMPANY_URL}/{slug}/"
            for attempt in range(3):
                resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning(
                        "fetch_fundamentals(%s): HTTP 429 (standalone), retrying in %ds",
                        symbol, wait
                    )
                    time.sleep(wait)
                    continue
                break

        if resp.status_code != 200:
            logger.warning(
                "fetch_fundamentals(%s): HTTP %d", symbol, resp.status_code
            )
            return {}

        soup = BeautifulSoup(resp.text, "html.parser")

        # Parse the #top-ratios section
        ratios = {}
        top_ratios = soup.find(id="top-ratios")
        if top_ratios:
            for li in top_ratios.find_all("li"):
                name_el = li.find("span", class_="name")
                value_el = li.find("span", class_="value")
                if name_el and value_el:
                    name = name_el.get_text(strip=True)
                    value = value_el.get_text(strip=True)
                    ratios[name] = value

        quarterly_growth = _extract_quarterly_growth(soup)
        sales_growth = _extract_sales_growth(soup)
        promoter_holding = _extract_promoter_holding(soup)
        debt_equity = _extract_debt_equity(soup, ratios)

        raw = {
            "symbol": symbol,
            "market_cap": ratios.get("Market Cap", ""),
            "pe": ratios.get("Stock P/E", ""),
            "roce": ratios.get("ROCE", ""),
            "roe": ratios.get("ROE", ""),
            "book_value": ratios.get("Book Value", ""),
            "dividend_yield": ratios.get("Dividend Yield", ""),
            "quarterly_revenue_growth": quarterly_growth,
            "sales_growth_3yr": sales_growth.get("3yr", ""),
            "sales_growth_5yr": sales_growth.get("5yr", ""),
            "promoter_holding_pct": promoter_holding,
            "debt_equity": debt_equity,
            "screener_url": url,
        }

        logger.info(
            "fetch_fundamentals(%s): PE=%s ROCE=%s ROE=%s growth_3yr=%s",
            symbol,
            raw["pe"],
            raw["roce"],
            raw["roe"],
            raw["sales_growth_3yr"],
        )
        return raw

    except Exception as exc:
        logger.error(
            "fetch_fundamentals(%s) failed: %s: %s",
            symbol,
            type(exc).__name__,
            exc,
        )
        return {}


def _extract_quarterly_growth(soup) -> str:
    """Extract most recent quarter revenue YoY growth %."""
    try:
        section = soup.find(id="quarters")
        if not section:
            return ""
        table = section.find("table")
        if not table:
            return ""
        rows = table.find_all("tr")
        for row in rows:
            if "Sales" in row.get_text():
                cells = row.find_all("td")
                if len(cells) >= 2:
                    # cells[0] is the row label, data starts at cells[1]
                    # take the last two data cells: year-ago vs most recent
                    data_cells = cells[1:]
                    if len(data_cells) >= 2:
                        recent_str = data_cells[-1].get_text(strip=True).replace(",", "")
                        year_ago_str = data_cells[-5].get_text(strip=True).replace(",", "") if len(data_cells) >= 5 else data_cells[0].get_text(strip=True).replace(",", "")
                        try:
                            recent = float(recent_str)
                            year_ago = float(year_ago_str)
                            if year_ago > 0:
                                growth = ((recent - year_ago) / year_ago) * 100
                                return f"{growth:+.1f}%"
                        except ValueError:
                            pass
    except Exception:
        pass
    return ""


def _extract_sales_growth(soup) -> dict:
    """Extract compounded SALES growth rates from the profit-loss section.

    The page has multiple '3 Years' / '5 Years' rows (sales, profit, price CAGR,
    ROE). We only want the block that immediately follows the
    'Compounded Sales Growth' header row.
    """
    result = {}
    try:
        pl = soup.find(id="profit-loss")
        if not pl:
            return result
        rows = pl.find_all("tr")
        in_sales_block = False
        for row in rows:
            th = row.find("th")
            if th and "Compounded Sales Growth" in th.get_text():
                in_sales_block = True
                continue
            if in_sales_block:
                # Stop if we hit another <th> block (next metric)
                if row.find("th"):
                    break
                cells = row.find_all("td")
                if len(cells) == 2:
                    label = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    if "3 Years" in label:
                        result["3yr"] = value
                    elif "5 Years" in label:
                        result["5yr"] = value
    except Exception:
        pass
    return result


def _extract_promoter_holding(soup) -> str:
    """Extract current promoter holding % from shareholding section."""
    try:
        section = soup.find(id="shareholding")
        if not section:
            return ""
        for row in section.find_all("tr"):
            if "Promoter" in row.get_text():
                cells = row.find_all("td")
                if cells:
                    return cells[-1].get_text(strip=True)
    except Exception:
        pass
    return ""


def _extract_debt_equity(soup, ratios: dict) -> str:
    """Compute debt/equity from the balance sheet.

    Screener doesn't expose D/E directly in top-ratios for all stocks.
    We take the most recent 'Borrowings' and divide by 'Equity Capital + Reserves'
    from the balance sheet table.
    """
    # Check top-ratios first (some stock pages do include it)
    for key in ("Debt to equity", "Debt / Equity", "D/E", "Debt/Eq"):
        if key in ratios:
            return ratios[key]

    try:
        bs = soup.find(id="balance-sheet")
        if not bs:
            return ""

        def _last_value(label: str) -> float | None:
            for row in bs.find_all("tr"):
                if label in row.get_text():
                    cells = row.find_all("td")
                    # Skip the onclick/expand cell if present
                    data = [
                        c.get_text(strip=True).replace(",", "")
                        for c in cells
                        if c.get_text(strip=True).replace(",", "").lstrip("-").replace(".", "", 1).isdigit()
                    ]
                    if data:
                        try:
                            return float(data[-1])
                        except ValueError:
                            pass
            return None

        borrowings = _last_value("Borrowings")
        equity_cap = _last_value("Equity Capital")
        reserves = _last_value("Reserves")

        if borrowings is not None and equity_cap is not None and reserves is not None:
            equity = equity_cap + reserves
            if equity > 0:
                de = borrowings / equity
                return f"{de:.2f}"
    except Exception:
        pass
    return ""


if __name__ == "__main__":
    import json

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    for symbol in ["UNOMINDA", "JPPOWER", "INOXGREEN"]:
        print(f"\n--- {symbol} ---")
        data = fetch_fundamentals(symbol)
        if data:
            print(json.dumps(data, indent=2))
        else:
            print("No data returned")
        time.sleep(3)  # be polite to Screener.in
