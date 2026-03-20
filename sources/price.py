import logging

import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_stock_context(ticker: str) -> dict:
    """Fetch current price and key context for a stock.

    ticker: NSE symbol like "JPPOWER" or "UNOMINDA"
    Appends .NS automatically if not present.

    Returns dict with:
    - ticker: str
    - current_price: float
    - day_change_pct: float
    - week_52_high: float
    - week_52_low: float
    - pct_from_52w_high: float  (negative means below high)
    - pct_from_52w_low: float   (positive means above low)
    - market_cap_cr: float      (in crores)
    - summary: str              (one line for alert)

    Returns {} on failure — alert proceeds without price context.
    """
    try:
        symbol = ticker.upper().strip()
        if not symbol.endswith(".NS"):
            symbol = symbol + ".NS"

        stock = yf.Ticker(symbol)
        info = stock.info

        current = info.get("currentPrice") or info.get("regularMarketPrice") or 0.0
        high_52 = info.get("fiftyTwoWeekHigh") or 0.0
        low_52 = info.get("fiftyTwoWeekLow") or 0.0
        prev_close = info.get("previousClose") or current
        mktcap = info.get("marketCap") or 0

        if not current:
            logger.warning("fetch_stock_context(%s): no price data", ticker)
            return {}

        day_change_pct = (
            round(((current - prev_close) / prev_close) * 100, 2)
            if prev_close else 0.0
        )
        pct_from_high = (
            round(((current - high_52) / high_52) * 100, 2)
            if high_52 else 0.0
        )
        pct_from_low = (
            round(((current - low_52) / low_52) * 100, 2)
            if low_52 else 0.0
        )
        mktcap_cr = round(mktcap / 1e7, 0) if mktcap else 0.0

        summary = (
            f"₹{current} ({'+' if day_change_pct >= 0 else ''}{day_change_pct}% today) | "
            f"52W: ₹{low_52}–₹{high_52} | "
            f"{abs(pct_from_high):.1f}% from 52W high | "
            f"Mkt Cap: ₹{mktcap_cr:.0f} Cr"
        )

        logger.info("fetch_stock_context(%s): ₹%.2f, %+.1f%% today", symbol, current, day_change_pct)
        return {
            "ticker": symbol,
            "current_price": current,
            "day_change_pct": day_change_pct,
            "week_52_high": high_52,
            "week_52_low": low_52,
            "pct_from_52w_high": pct_from_high,
            "pct_from_52w_low": pct_from_low,
            "market_cap_cr": mktcap_cr,
            "summary": summary,
        }
    except Exception as exc:
        logger.warning("fetch_stock_context(%s) failed: %s", ticker, exc)
        return {}


if __name__ == "__main__":
    import json
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    for t in ["JPPOWER", "UNOMINDA", "RELIANCE"]:
        print(f"\n--- {t} ---")
        ctx = fetch_stock_context(t)
        if ctx:
            print(json.dumps(ctx, indent=2))
        else:
            print("No data")
