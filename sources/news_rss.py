import logging
import re
from urllib.parse import quote_plus

import feedparser
import requests

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; agentmesh/1.0)"}

RBI_RSS_URLS = [
    "https://www.rbi.org.in/pressreleases_rss.xml",
    "https://www.rbi.org.in/notifications_rss.xml",
]
SEBI_RSS_URL = "https://www.sebi.gov.in/sebirss.xml"


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _is_actionable_sebi_item(title: str) -> bool:
    """
    SEBI feed is mostly enforcement noise. Only pass through items
    that could affect markets or trading rules.
    """
    title_lower = title.lower()

    skip_keywords = [
        "recovery certificate", "notice of demand", "prohibitory order",
        "release order", "notice of attachment", "adjudication order",
        "completion of recovery", "cancellation of recovery",
        "illiquid stock options", "defaulter",
    ]
    if any(kw in title_lower for kw in skip_keywords):
        return False

    keep_keywords = [
        "circular", "regulation", "framework", "consultation",
        "discussion paper", "policy", "guideline", "amendment",
        "settlement scheme", "new rule", "market", "mutual fund",
        "ipo", "listing", "disclosure", "trading", "derivative",
    ]
    return any(kw in title_lower for kw in keep_keywords)


def fetch_google_news(query: str) -> list[dict]:
    """Fetch up to 10 recent Google News RSS entries matching query.

    Returns list of dicts with keys: title, source, published, url, summary.
    Returns [] on any failure.
    """
    try:
        url = (
            f"https://news.google.com/rss/search"
            f"?q={quote_plus(query)}&hl=en-IN&gl=IN&ceid=IN:en"
        )
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        entries = feed.entries[:10]
        results = []
        for e in entries:
            source = ""
            if hasattr(e, "source") and hasattr(e.source, "title"):
                source = e.source.title

            results.append({
                "title": e.get("title", ""),
                "source": source,
                "published": e.get("published", ""),
                "url": e.get("link", ""),
                "summary": _strip_html(e.get("summary", "")),
            })
        logger.info("fetch_google_news(%r): fetched %d entries", query, len(results))
        return results
    except Exception as exc:
        logger.error("fetch_google_news failed: %s: %s", type(exc).__name__, exc)
        return []


def fetch_rbi_rss() -> list[dict]:
    """Fetch up to 15 recent RBI RSS entries (press releases + notifications).

    Combines both feeds, deduplicates by URL, sorts by published date.
    Returns list of dicts with keys: title, published, url, summary.
    Returns [] on any failure.
    """
    try:
        seen_urls: set[str] = set()
        combined: list[dict] = []

        for rss_url in RBI_RSS_URLS:
            resp = requests.get(rss_url, headers=_HEADERS, timeout=15)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
            for e in feed.entries:
                url = e.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                combined.append({
                    "title": e.get("title", ""),
                    "published": e.get("published", ""),
                    "url": url,
                    "summary": _strip_html(e.get("summary", "")),
                })

        combined.sort(key=lambda x: x["published"], reverse=True)
        results = combined[:15]
        logger.info("fetch_rbi_rss: fetched %d entries", len(results))
        return results
    except Exception as exc:
        logger.error("fetch_rbi_rss failed: %s: %s", type(exc).__name__, exc)
        return []


def fetch_sebi_rss() -> list[dict]:
    """Fetch up to 10 actionable SEBI RSS entries (enforcement noise filtered out).

    Returns list of dicts with keys: title, published, url, summary.
    Returns [] on any failure.
    """
    try:
        resp = requests.get(SEBI_RSS_URL, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        all_entries = feed.entries
        logger.info("fetch_sebi_rss: fetched %d raw entries", len(all_entries))

        results = []
        for e in all_entries:
            title = e.get("title", "")
            if not _is_actionable_sebi_item(title):
                continue
            results.append({
                "title": title,
                "published": e.get("published", ""),
                "url": e.get("link", ""),
                "summary": _strip_html(e.get("summary", "")),
            })
            if len(results) == 10:
                break

        logger.info("fetch_sebi_rss: %d entries after filter", len(results))
        return results
    except Exception as exc:
        logger.error("fetch_sebi_rss failed: %s: %s", type(exc).__name__, exc)
        return []


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    print("\n--- Google News: NSE India market ---")
    news = fetch_google_news("NSE India stock market")
    print(f"Total: {len(news)}")
    for n in news[:3]:
        print(f"  {n['title']} — {n.get('source', '')}")

    print("\n--- RBI ---")
    rbi = fetch_rbi_rss()
    print(f"Total: {len(rbi)}")
    for r in rbi[:3]:
        print(f"  {r['title']}")

    print("\n--- SEBI (filtered) ---")
    sebi = fetch_sebi_rss()
    print(f"Total after filter: {len(sebi)}")
    for s in sebi[:3]:
        print(f"  {s['title']}")
