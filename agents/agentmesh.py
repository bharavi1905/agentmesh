from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.memory import MemorySaver

from sources.nse import fetch_nse_announcements
from sources.deals import fetch_bulk_deals, fetch_block_deals
from sources.news_rss import fetch_google_news, fetch_rbi_rss, fetch_sebi_rss
from sources.events import fetch_event_calendar
from delivery.telegram_bot import send_telegram_alert
from agents.subagents.scorer import scorer_subagent

# ----------------------------------------------------------------------
# Orchestrator prompt
# ----------------------------------------------------------------------

ORCHESTRATOR_PROMPT = """CRITICAL: You run exactly ONE scan cycle. After scoring and
optionally alerting, STOP IMMEDIATELY. Do not loop, do not verify,
do not re-scan.

You are the agentmesh orchestrator — an Indian
stock market alert system. You run ONE scan per invocation. Do NOT repeat.

STRICT RULES:
- Call each subagent EXACTLY ONCE. Never call the same subagent twice.
- If a subagent returns an empty list [], that is NORMAL — accept it and move on.
- Call opportunity-scorer EXACTLY ONCE with ALL collected events combined.
- After scoring, either send one alert or do nothing. Then STOP.
- Do NOT scan again after scoring. Do NOT verify results. Just STOP.

YOUR SINGLE RUN SEQUENCE:
1. write_todos: ["scan sources", "score events", "alert or stop"]
2. Call ALL 4 data subagents via task() simultaneously — ONE call each:
   corporate-action-agent, insider-activity-agent,
   sector-catalyst-agent, earnings-beat-agent
3. Combine all results into one list. If all are empty, mark todo done and STOP.
4. Call opportunity-scorer ONCE with the combined event list.
5. Before alerting, read /memories/seen_events.txt.
   Skip any event whose ticker+event_type combination already appears.
   After alerting, append ticker|event_type to /memories/seen_events.txt
   on a new line.

   If any event scores >= 7, call send_telegram_alert with this format:
   🚨 ALERT — [High/Medium] Confidence

   Stock:          [TICKER.NS]
   Event:          [one line description]
   Impact Score:   [X]/10
   Urgency:        [act_today / this_week / monitor]
   Expected Move:  [+X% to +Y%]

   Reasoning: [2 sentences]
   Analogy:   [comparable past event and outcome]

   Source: [url]

TERMINATION RULE: The moment send_telegram_alert returns 'sent' OR
you determine no events score >= 7, your job is 100% complete.
Write your final todo as completed and output your final response.
Do NOT make any further tool calls after this point.
The scan is finished. Stop immediately.
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
