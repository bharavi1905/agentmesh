import io
import logging
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from utils.config import NSE_EQUITY_LIST_URL

logger = logging.getLogger(__name__)

CACHE_PATH = Path(__file__).parent.parent / "data" / "nse_equity.csv"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# In-memory set of valid NSE symbols — loaded once at import time
_valid_symbols: set[str] = set()
_company_names: dict[str, str] = {}  # SYMBOL -> NAME OF COMPANY


def _download_equity_list() -> pd.DataFrame:
    """Download EQUITY_L.csv from NSE archives."""
    resp = requests.get(NSE_EQUITY_LIST_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    df = pd.read_csv(io.BytesIO(resp.content))
    df.columns = df.columns.str.strip()
    return df


def _load_equity_list() -> None:
    """Load NSE equity list into memory. Downloads if not cached or stale."""
    global _valid_symbols, _company_names

    # Use cached file if it exists and is less than 7 days old
    if CACHE_PATH.exists():
        age = date.today() - date.fromtimestamp(CACHE_PATH.stat().st_mtime)
        if age < timedelta(days=7):
            df = pd.read_csv(CACHE_PATH)
            df.columns = df.columns.str.strip()
            _valid_symbols = set(df["SYMBOL"].str.strip().str.upper())
            _company_names = dict(
                zip(
                    df["SYMBOL"].str.strip().str.upper(),
                    df["NAME OF COMPANY"].str.strip(),
                )
            )
            logger.info(
                "nse_symbols: loaded %d symbols from cache", len(_valid_symbols)
            )
            return

    # Download fresh copy
    try:
        logger.info("nse_symbols: downloading fresh equity list from NSE...")
        df = _download_equity_list()
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(CACHE_PATH, index=False)
        _valid_symbols = set(df["SYMBOL"].str.strip().str.upper())
        _company_names = dict(
            zip(
                df["SYMBOL"].str.strip().str.upper(),
                df["NAME OF COMPANY"].str.strip(),
            )
        )
        logger.info("nse_symbols: downloaded %d symbols", len(_valid_symbols))
    except Exception as exc:
        logger.error("nse_symbols: download failed: %s — using empty set", exc)
        _valid_symbols = set()
        _company_names = {}


def is_valid_nse_symbol(symbol: str) -> bool:
    """Return True if symbol is a confirmed NSE-listed equity."""
    if not _valid_symbols:
        _load_equity_list()
    clean = symbol.upper().strip().replace(".NS", "").replace(".BO", "")
    return clean in _valid_symbols


def get_company_name(symbol: str) -> str:
    """Return full company name for a symbol, or empty string."""
    clean = symbol.upper().strip().replace(".NS", "").replace(".BO", "")
    return _company_names.get(clean, "")


# Load on import — fast from cache, one-time download if needed
_load_equity_list()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s"
    )

    tests = [
        "TEXMACO",      # invalid — subagent should return TEXRAIL
        "TEXMRAIL",     # invalid — subagent should return TEXRAIL
        "TEXRAIL",      # valid ✅
        "SHREECEM",     # valid ✅
        "SHREE",        # invalid — not an NSE symbol
        "UNOMINDA",     # valid ✅
        "BEL",          # valid ✅
        "PSU",          # invalid ✅
        "INFRA",        # invalid ✅
        "RELIANCE",     # valid ✅
    ]

    for t in tests:
        valid = is_valid_nse_symbol(t)
        name = get_company_name(t) if valid else ""
        status = "✅ valid" if valid else "❌ invalid"
        print(f"{t:20} {status:12} {name}")
