from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.memory import MemorySaver

from utils.config import NSE_BULK_DEALS_PAGE, NSE_BLOCK_DEALS_PAGE
from sources.nse import fetch_nse_announcements
from sources.deals import fetch_bulk_deals, fetch_block_deals
from sources.news_rss import fetch_google_news, fetch_rbi_rss, fetch_sebi_rss
from sources.events import fetch_event_calendar
from sources.fii_dii import fetch_fii_dii_flows
from sources.price import fetch_stock_context
from utils.market_calendar import is_market_open_today
from utils.enrichment import prefetch_enrichment
from delivery.telegram_bot import send_telegram_alert
from agents.subagents.scorer import scorer_subagent

# ----------------------------------------------------------------------
# Orchestrator prompt
# ----------------------------------------------------------------------

ORCHESTRATOR_PROMPT = """You are a stock market alert system for India.

CRITICAL: You run exactly ONE scan cycle. After scoring and optionally
alerting, STOP IMMEDIATELY. Do not loop, do not verify, do not re-scan.

Each scan run — do this exactly once in order:
1. write_todos: ["scan sources", "prefetch enrichment", "score events", "alert or stop"]
2. Call ALL 5 subagents simultaneously via task() — ONE call each:
   corporate-action-agent, insider-activity-agent,
   sector-catalyst-agent, earnings-beat-agent, macro-context-agent
3. Combine all results. If all data is empty, mark todos done and STOP.
4. Extract all candidate tickers from the collected events (any event
   that looks like it could score >= 5). Call prefetch_enrichment()
   ONCE with the full list of tickers. This fetches price and
   fundamentals for all candidates in parallel.
5. Call opportunity-scorer ONCE with ALL events (no enrichment data).
   This is BATCH SCREENING MODE — gets raw scores quickly.

   Then for each event with raw_score >= 6 from the batch screen,
   call opportunity-scorer again INDIVIDUALLY — one task() call per
   event — passing that single event PLUS its enrichment data from
   prefetch_enrichment (price_context + fundamentals for that ticker)
   PLUS the FII/DII context. This is SINGLE EVENT MODE.

   Only send alerts for events that score >= 7 after all modifiers
   in the individual scoring call.
6. Before alerting, read /memories/seen_events.txt.
   Skip any event whose ticker+event_type already appears there.
   After alerting, append ticker|event_type to /memories/seen_events.txt.

   For each event scoring >= 7, call send_telegram_alert with this format:
   🚨 ALERT — [High/Medium] Confidence

   <b>Stock:</b>          [affected_ticker]
   <b>Price:</b>          [price_context — if empty or 'Price data unavailable', show: 'Price data unavailable — verify on NSE']
   <b>Event:</b>          [one line description]
   <b>Impact Score:</b>   [impact_score]/10 (raw [raw_score][", FII [fii_adjustment shown as e.g. -1 or +1]" if non-zero][", fundamentals [fund_adjustment]" if non-zero][", no adjustments" if both zero])
   <b>Urgency:</b>        [act_today / this_week / monitor]
   <b>Expected Move:</b>  [expected_move_pct]

   <b>Reasoning:</b> [reasoning]
   <b>Analogy:</b>   [historical_analogy]
   <b>FII Today:</b> [fii_context]

   [fundamentals_narrative — include exactly as returned by scorer, with emoji and HTML bold tags intact. Omit entirely if empty string.]

   <b>Source:</b>  <a href="[url]">[display_text]</a>
   where display_text is determined by the url:
   - 'View article' if url contains 'news.google.com'
   - 'NSE bulk deals' if url contains 'bulk-deals'
   - 'NSE block deals' if url contains 'block-deals'
   - 'NSE announcements' if url contains 'corporate-announcements'
   - the full url otherwise
   <b>Verify:</b>  [screener_url — omit this line entirely if screener_url is empty]

STRICT RULES:
- Call each subagent EXACTLY ONCE. Never call the same subagent twice.
- If a subagent returns an empty list or {}, that is NORMAL — accept it.
- Call opportunity-scorer once for batch screening, then once per
  candidate event (raw_score >= 6) for individual complete scoring.
- IMPORTANT: Do NOT write any files. Return results as JSON in text only.

TERMINATION RULE: The moment all send_telegram_alert calls complete OR
you determine no events score >= 7, your job is 100% complete.
Write your final todo as completed and output your final response.
Do NOT make any further tool calls after this point. Stop immediately.
"""

# ----------------------------------------------------------------------
# Data-collection subagents
# ----------------------------------------------------------------------

corporate_action_subagent = {
    "name": "corporate-action-agent",
    "description": (
        "Fetches and analyses NSE corporate announcements. Use when scanning "
        "for M&A, buybacks, demergers, or board meeting notices."
    ),
    "system_prompt": """You scan NSE corporate announcements for high-impact events.
Focus on: M&A, acquisitions, buybacks, demergers, fundraising board meetings.
Ignore: AGM notices, dividend declarations under 5%, routine updates.
Return a JSON list of events with fields: ticker, event_type, summary, raw_url.

Call fetch_nse_announcements() EXACTLY ONCE. Do not call it again.
Return your JSON list immediately after the first call. Do not verify
or re-fetch.

IMPORTANT: Do NOT write any files. Do NOT use write_file or any
filesystem tools. Return your results as a JSON list in your text
response only.

Return only confirmed NSE-listed ticker symbols.
Examples of correct symbols: TEXRAIL (not TEXMACO), SHREECEM (not SHREE),
RELIANCE, BEL, UNOMINDA.
If unsure of the exact NSE symbol, use ticker: 'UNKNOWN'.
Never guess — wrong tickers waste the entire enrichment pipeline.""",
    "tools": [fetch_nse_announcements],
    "model": "openai:gpt-4.1-mini",
}

insider_activity_subagent = {
    "name": "insider-activity-agent",
    "description": (
        "Fetches NSE bulk deals and block deals. Use when scanning for "
        "promoter buying, institutional accumulation, or large insider trades."
    ),
    "system_prompt": f"""You scan NSE bulk deals and block deals for insider signals.
Focus on: promoter increases >1%, institutional buying >5cr, promoter selling (bearish).
Return JSON list: ticker, deal_type, buyer_seller, quantity, value_cr, signal (bullish/bearish), source_url.

For bulk deals use source_url: '{NSE_BULK_DEALS_PAGE}'
For block deals use source_url: '{NSE_BLOCK_DEALS_PAGE}'
Always include the correct source_url in your JSON output.

Return only confirmed NSE-listed ticker symbols.
Examples of correct symbols: TEXRAIL (not TEXMACO), SHREECEM (not SHREE),
RELIANCE, BEL, UNOMINDA.
If unsure of the exact NSE symbol, use ticker: 'UNKNOWN'.
Never guess — wrong tickers waste the entire enrichment pipeline.""",
    "tools": [fetch_bulk_deals, fetch_block_deals],
    "model": "openai:gpt-4.1-mini",
}

sector_catalyst_subagent = {
    "name": "sector-catalyst-agent",
    "description": (
        "Monitors news for government contracts, PLI schemes, policy announcements "
        "that benefit specific listed companies or sectors."
    ),
    "system_prompt": """You scan news for sector-level catalysts affecting NSE-listed stocks.
Focus on: defence contracts, railway orders, infra tenders, PLI approvals, capex announcements.
For each event return: affected_tickers (list), sector, catalyst_summary, estimated_impact.

IMPORTANT: Call fetch_google_news() a maximum of 3 times with DIFFERENT specific queries.
If a query returns 0 results, do NOT retry with a rephrased version of the same query.
Accept 0 results and move on. Return whatever you found.

Return only confirmed NSE-listed ticker symbols.
Examples of correct symbols: TEXRAIL (not TEXMACO), SHREECEM (not SHREE),
RELIANCE, BEL, UNOMINDA.
If unsure of the exact NSE symbol, use ticker: 'UNKNOWN'.
Never guess — wrong tickers waste the entire enrichment pipeline.""",
    "tools": [fetch_google_news, fetch_rbi_rss, fetch_sebi_rss],
    "model": "openai:gpt-4.1-mini",
}

earnings_beat_subagent = {
    "name": "earnings-beat-agent",
    "description": (
        "Checks NSE results calendar for recent earnings and flags significant "
        "beats or misses vs analyst estimates."
    ),
    "system_prompt": """You scan the NSE results calendar and identify earnings surprises.
A beat is significant if actual > estimate by >10%. A miss if actual < estimate by >10%.
Return JSON: ticker, reported_eps, estimated_eps, surprise_pct, beat_or_miss.

Return only confirmed NSE-listed ticker symbols.
Examples of correct symbols: TEXRAIL (not TEXMACO), SHREECEM (not SHREE),
RELIANCE, BEL, UNOMINDA.
If unsure of the exact NSE symbol, use ticker: 'UNKNOWN'.
Never guess — wrong tickers waste the entire enrichment pipeline.""",
    "tools": [fetch_event_calendar, fetch_google_news, fetch_rbi_rss],
    "model": "openai:gpt-4.1-mini",
}

macro_context_subagent = {
    "name": "macro-context-agent",
    "description": (
        "Fetches today's FII and DII institutional flow data. "
        "Always call this — it provides confidence context for scoring."
    ),
    "system_prompt": """Fetch today's FII/DII flows using fetch_fii_dii_flows().
Return a brief JSON:
{
  "fii_net_cr": <float>,
  "dii_net_cr": <float>,
  "sentiment": "bullish|bearish|neutral",
  "context": "<one sentence for scorer>"
}
Call fetch_fii_dii_flows() EXACTLY ONCE. Return the result immediately.""",
    "tools": [fetch_fii_dii_flows],
    "model": "openai:gpt-4.1-mini",
}

# ----------------------------------------------------------------------
# Backend — cross-run deduplication via CompositeBackend + StoreBackend
# ----------------------------------------------------------------------

store = InMemoryStore()  # swap for PostgresStore in production


def make_backend(runtime):
    return CompositeBackend(
        default=StateBackend(runtime),           # ephemeral scratch space per run
        routes={"/memories/": StoreBackend(runtime)},  # persists seen events across runs
    )


# ----------------------------------------------------------------------
# Main orchestrator agent
# ----------------------------------------------------------------------

agent = create_deep_agent(
    model="openai:gpt-5-mini",
    system_prompt=ORCHESTRATOR_PROMPT,
    tools=[fetch_nse_announcements, prefetch_enrichment, send_telegram_alert],
    subagents=[
        corporate_action_subagent,
        insider_activity_subagent,
        sector_catalyst_subagent,
        earnings_beat_subagent,
        macro_context_subagent,
        scorer_subagent,
    ],
    backend=make_backend,
    store=store,
    checkpointer=MemorySaver(),
    name="agentmesh-orchestrator",
)


# ----------------------------------------------------------------------
# run_scan — called by the APScheduler in main.py
# ----------------------------------------------------------------------

def run_scan():
    import logging
    logger = logging.getLogger(__name__)

    # if not is_market_open_today():
    #     logger.info("Market is closed today — skipping scan")
    #     return

    try:
        result = agent.stream(
            {"messages": [{"role": "user", "content": (
                "Scan all market sources once and alert if anything "
                "scores >= 7. Run each subagent exactly once. "
                "Stop after scoring."
            )}]},
            config={
                "configurable": {"thread_id": "agentmesh-main"},
                "recursion_limit": 50,
            },
            stream_mode="updates",
            subgraphs=True,
            version="v2",
        )
        for chunk in result:
            if chunk["type"] == "updates":
                source = f"[{chunk['ns'][0]}]" if chunk["ns"] else "[orchestrator]"
                for node in chunk["data"]:
                    print(f"{source} → {node}")
    except Exception as e:
        if "recursion" in str(e).lower():
            logger.warning(
                "Scan hit recursion limit — orchestrator looped too many times"
            )
        else:
            logger.error("Scan error: %s: %s", type(e).__name__, e)


if __name__ == "__main__":
    import utils.config  # noqa: F401 — loads .env so API keys hit os.environ
    run_scan()
