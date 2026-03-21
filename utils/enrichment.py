import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from sources.fundamentals import fetch_fundamentals
from sources.price import fetch_stock_context
from utils.nse_symbols import is_valid_nse_symbol

logger = logging.getLogger(__name__)


def prefetch_enrichment(tickers: list[str]) -> dict:
    """Fetch price and fundamentals for multiple tickers in parallel.

    Call this BEFORE passing events to the scorer.
    Returns dict keyed by clean symbol (no .NS suffix).

    {
      "UNOMINDA": {
        "price_context": "Rs 1067.0 (+2.65% today) | ...",
        "fundamentals": { "pe": "53.2", "roce": "18.8%", ... }
      }
    }
    """
    if not tickers:
        return {}

    # Validate all tickers against NSE equity list — no correction, validate only
    validated = []
    for raw in tickers:
        clean = raw.upper().replace(".NS", "").replace(".BO", "").strip()
        if is_valid_nse_symbol(clean):
            validated.append(clean)
            logger.info(
                "prefetch_enrichment: ✓ '%s' is valid NSE symbol", clean
            )
        else:
            logger.warning(
                "prefetch_enrichment: ✗ skipping '%s' — not in NSE equity list", raw
            )

    if not validated:
        return {}

    # Deduplicate while preserving order
    seen: set[str] = set()
    deduped = []
    for s in validated:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    validated = deduped

    results = {}

    def fetch_one(symbol: str, delay: float = 0.0):
        time.sleep(delay)
        price = fetch_stock_context(f"{symbol}.NS")
        if not price:
            price = fetch_stock_context(f"{symbol}.BO")
        fundamentals = fetch_fundamentals(symbol)
        return symbol, price, fundamentals

    logger.info(
        "prefetch_enrichment: fetching %d validated tickers in parallel",
        len(validated),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(fetch_one, symbol, i * 0.5): symbol
            for i, symbol in enumerate(validated)
        }
        try:
            for future in as_completed(futures, timeout=60):
                try:
                    symbol, price, fundamentals = future.result(timeout=15)
                    results[symbol] = {
                        "price_context": price.get("summary", ""),
                        "fundamentals": fundamentals,
                    }
                    logger.info(
                        "prefetch_enrichment: %s — price=%s, fundamentals=%s",
                        symbol,
                        "ok" if price else "missing",
                        "ok" if fundamentals else "missing",
                    )
                except TimeoutError:
                    symbol = futures[future]
                    logger.warning(
                        "prefetch_enrichment: %s timed out — skipping", symbol
                    )
                except Exception as exc:
                    symbol = futures[future]
                    logger.warning(
                        "prefetch_enrichment(%s) failed: %s", symbol, exc
                    )
        except TimeoutError:
            logger.warning(
                "prefetch_enrichment: overall timeout — completed %d/%d tickers",
                len(results),
                len(validated),
            )

    logger.info(
        "prefetch_enrichment: completed %d/%d tickers",
        len(results),
        len(validated),
    )
    return results
