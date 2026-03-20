from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.memory import MemorySaver

from sources.nse import fetch_nse_announcements
from sources.deals import fetch_bulk_deals, fetch_block_deals
from sources.news_rss import fetch_google_news, fetch_rbi_rss, fetch_sebi_rss
from sources.events import fetch_event_calendar
from sources.fii_dii import fetch_fii_dii_flows
from sources.price import fetch_stock_context
from utils.market_calendar import is_market_open_today
from delivery.telegram_bot import send_telegram_alert
from agents.subagents.scorer import scorer_subagent

# ----------------------------------------------------------------------
# Orchestrator prompt
# ----------------------------------------------------------------------

ORCHESTRATOR_PROMPT = """You are a stock market alert system for India.

CRITICAL: You run exactly ONE scan cycle. After scoring and optionally
alerting, STOP IMMEDIATELY. Do not loop, do not verify, do not re-scan.

Each scan run — do this exactly once in order:
1. write_todos: ["scan sources", "score events", "alert or stop"]
2. Call ALL 5 subagents simultaneously via task() — ONE call each:
   corporate-action-agent, insider-activity-agent,
   sector-catalyst-agent, earnings-beat-agent, macro-context-agent
3. Combine all results. If all data is empty, mark todos done and STOP.
4. Call opportunity-scorer EXACTLY ONCE with ALL collected events
   plus the FII/DII context from macro-context-agent.
5. Before alerting, read /memories/seen_events.txt.
   Skip any event whose ticker+event_type already appears there.
   After alerting, append ticker|event_type to /memories/seen_events.txt.

   For each event scoring >= 7, call send_telegram_alert with this format:
   🚨 ALERT — [High/Medium] Confidence

   Stock:          [TICKER.NS]
   Price:          [price_context summary line from scorer]
   Event:          [one line description]
   Impact Score:   [X]/10
   Urgency:        [act_today / this_week / monitor]
   Expected Move:  [+X% to +Y%]

   Reasoning: [2 sentences]
   Analogy:   [comparable past event and outcome]
   FII Today: [fii_context one line from macro-context-agent]

   Source: [url]

STRICT RULES:
- Call each subagent EXACTLY ONCE. Never call the same subagent twice.
- If a subagent returns an empty list or {}, that is NORMAL — accept it.
- Call opportunity-scorer EXACTLY ONCE.
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
response only.""",
    "tools": [fetch_nse_announcements],
    "model": "openai:gpt-4.1-mini",
}

insider_activity_subagent = {
    "name": "insider-activity-agent",
    "description": (
        "Fetches NSE bulk deals and block deals. Use when scanning for "
        "promoter buying, institutional accumulation, or large insider trades."
    ),
    "system_prompt": """You scan NSE bulk deals and block deals for insider signals.
Focus on: promoter increases >1%, institutional buying >5cr, promoter selling (bearish).
Return JSON list: ticker, deal_type, buyer_seller, quantity, value_cr, signal (bullish/bearish).""",
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
For each event return: affected_tickers (list), sector, catalyst_summary, estimated_impact.""",
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
Return JSON: ticker, reported_eps, estimated_eps, surprise_pct, beat_or_miss.""",
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
    tools=[fetch_nse_announcements, send_telegram_alert],
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

    if not is_market_open_today():
        logger.info("Market is closed today — skipping scan")
        return

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
