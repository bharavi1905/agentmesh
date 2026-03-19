# agentmesh — Project Context

## What this project is

An AI-powered **multi-agent alert system** that monitors Indian stock market events and sends actionable alerts to the developer (via Telegram) when profitable business events are detected. The developer makes all final trading decisions — this system is a research and signal copilot, not an automated trader.

---

## Architecture: Agent Mesh

The system is a hierarchy of specialised agents, each with a focused role:

```
┌─────────────────────────────────────────────────────┐
│              Event Collector Agent                  │
│   Polls all data sources, deduplicates, normalises  │
└───────────┬─────────┬──────────┬──────────┬─────────┘
            │         │          │          │
    ┌───────▼──┐ ┌────▼────┐ ┌──▼──────┐ ┌─▼────────┐
    │Corporate │ │ Insider │ │ Sector  │ │ Earnings │
    │ Action   │ │Activity │ │Catalyst │ │  Beat    │
    │ Agent    │ │  Agent  │ │  Agent  │ │  Agent   │
    └───────┬──┘ └────┬────┘ └──┬──────┘ └─┬────────┘
            └─────────┴─────────┴───────────┘
                              │
                ┌─────────────▼─────────────┐
                │     Opportunity Scorer     │
                │  Rates: impact, confidence,│
                │  urgency per event         │
                └─────────────┬─────────────┘
                              │
                ┌─────────────▼─────────────┐
                │       Alert to User        │
                │   Telegram bot message     │
                │   with full context        │
                └───────────────────────────┘
```

### Agent roles

- **Event Collector**: Polls NSE/BSE endpoints, Google News RSS, RBI/SEBI RSS feeds. Deduplicates events using ChromaDB vector memory. Runs on a schedule.
- **Corporate Action Agent**: Detects M&A, demergers, splits, buybacks, board meetings with agenda hints.
- **Insider Activity Agent**: Watches NSE bulk deal / block deal data, promoter shareholding changes.
- **Sector Catalyst Agent**: Policy announcements, government contracts, PLI scheme updates, capex news.
- **Earnings Beat Agent**: Compares reported results vs analyst estimates, flags surprise magnitude.
- **Opportunity Scorer**: Claude API call that reads the normalised event and scores it on impact (1–10), confidence (high/medium/low), urgency (act today / this week / monitor).
- **Alert Delivery**: Telegram bot sends a structured message with event summary, stock affected, historical analogy, and suggested action window.

---

## Free Tier Tech Stack

All tools are free except Claude API (est. $2–5/month at light usage).

| Layer | Tool | Notes |
|---|---|---|
| Price data | `yfinance` | No API key. Use `.NS` suffix for NSE, `.BO` for BSE |
| Corporate filings | NSE/BSE public JSON endpoints | Unofficial but stable. Requires browser-like headers |
| News | Google News RSS + `feedparser` | Free, no key. Keyword-based search per company/sector |
| Regulatory | RBI + SEBI RSS feeds | Official feeds, poll hourly |
| LLM — orchestrator | `openai:gpt-5-mini` | Reliable stop behavior |
| LLM — subagents | `openai:gpt-4.1-mini` | Cheap, single-step only |
| Agent memory | ChromaDB (local) | Prevents re-alerting on same event. Free, runs locally |
| Alert delivery | Telegram Bot API + `python-telegram-bot` | Free. 5-minute setup |
| Agent framework | `langgraph` | Nodes, edges, GraphState, Send API for parallelism |
| Package manager | `uv` | Use `uv add <pkg>`, not pip. Commit `uv.lock` |

> **Important**: Claude Pro ($20/month, claude.ai) is the chat interface used to design this system.
> The Claude API (console.anthropic.com) is a **separate account** needed for the runtime scorer agent.
> Do not confuse the two. Set up API access at console.anthropic.com before wiring the scorer.

---

## Data Sources Detail

### NSE public endpoints

**Verified working endpoints (as of March 2026):**
```
Corporate announcements:  https://www.nseindia.com/api/corporate-announcements?index=equities
Results / events calendar: https://www.nseindia.com/api/event-calendar

Bulk deals (today):        https://www.nseindia.com/api/snapshot-capital-market-largedeal?index=bulk_deals
Block deals (today):       https://www.nseindia.com/api/snapshot-capital-market-largedeal?index=block_deals
Bulk deals (historical):   https://www.nseindia.com/api/snapshot-capital-market-largedeal?index=bulk_deals&from_date=01-03-2026&to_date=19-03-2026
```

**Broken — do NOT use:**
```
# These return 404 or empty data — replaced by snapshot-capital-market-largedeal above
https://www.nseindia.com/api/historical/bulk-deals
https://www.nseindia.com/api/live-analysis-data?index=block_deals
```

**Polling schedule — bulk/block deals are end-of-day only:**
```
corporate_announcements  → every 5 min, 9:00am–4:00pm IST (market hours only)
event_calendar           → once daily at 8:00am IST
bulk_deals               → once daily at 6:30pm IST (NSE publishes after market close)
block_deals              → once daily at 6:30pm IST
```

**Critical**: NSE blocks plain requests. Use a `requests.Session()` with these headers:
```python
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com",
    "Accept-Language": "en-US,en;q=0.9",
}
# First hit the main page to get cookies, then hit the API endpoint
session.get("https://www.nseindia.com", headers=headers)
data = session.get(api_url, headers=headers).json()
```

### Google News RSS (poll every 15 minutes)
```python
import feedparser
query = "Reliance Industries NSE acquisition"
url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
feed = feedparser.parse(url)
```

### RBI RSS
```
https://www.rbi.org.in/Scripts/rss.aspx
```

### SEBI RSS
```
https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRss=yes
```

### yfinance usage
```python
import yfinance as yf
ticker = yf.Ticker("RELIANCE.NS")   # NSE
hist = ticker.history(period="5d")
info = ticker.info  # includes market cap, PE, sector
```

---

## Event Types to Monitor

Priority order (highest signal first):

1. **M&A / Acquisition announcements** — target stock moves 20–40%
2. **Promoter bulk buying** — strong insider confidence signal
3. **Large government contracts** — defence, railways, infrastructure
4. **Earnings surprise > 15% vs estimate** — multi-day momentum
5. **Regulatory approvals** — NCLT orders, drug approvals (pharma), SEBI actions
6. **RBI/SEBI policy** — rate decisions, sector-specific circulars
7. **Block deals by institutional investors** — directional signal

---

## Alert Format Spec

Every alert sent to Telegram must follow this structure:

```
🚨 ALERT — [High / Medium] Confidence

Event:   [One line description of what happened]
Stock:   [TICKER.NS] — [Company Name]
Sector:  [Sector name]

Current price:  ₹[price]
Expected move:  [+X% to +Y%] based on [reasoning]
Analogy:        [Similar past event and its outcome]

Urgency:  [Act today / This week / Monitor]
Source:   [URL or filing reference]
Scored:   [timestamp]
```

Only send alerts scored **7/10 or above** on impact. Noisy low-quality alerts defeat the purpose.

---

## Suggested Project Structure

```
agentmesh/
├── CLAUDE.md                  ← this file
├── .env                       ← API keys (never commit)
├── pyproject.toml             ← dependencies managed by uv
├── uv.lock                    ← auto-generated, commit this
├── main.py                    ← entry point, starts APScheduler
│
├── agents/
│   ├── __init__.py
│   ├── agentmesh.py           ← create_deep_agent() call, registers all subagents
│   ├── subagents/
│   │   ├── __init__.py
│   │   ├── corporate_action.py    ← subagent dict + fetch_nse_announcements tool
│   │   ├── insider_activity.py    ← subagent dict + fetch_bulk/block deals tools
│   │   ├── sector_catalyst.py     ← subagent dict + news RSS tools
│   │   ├── earnings_beat.py       ← subagent dict + event calendar tools
│   │   └── scorer.py              ← subagent dict (no tools, pure LLM reasoning)
│   └── prompts.py             ← ORCHESTRATOR_PROMPT and subagent system prompts
│
├── sources/
│   ├── __init__.py
│   ├── nse.py                 ← NSE announcements + event calendar poller
│   ├── deals.py               ← bulk deals + block deals (snapshot-capital-market-largedeal)
│   └── news_rss.py            ← Google News RSS + RBI + SEBI feeds
│
├── delivery/
│   ├── __init__.py
│   └── telegram_bot.py        ← send_telegram_alert tool function
│
└── utils/
    ├── __init__.py
    ├── logger.py
    └── config.py              ← loads .env, exposes settings
```

---

## Environment Variables (.env)

```env
# Claude API (from console.anthropic.com — separate from Claude Pro)
ANTHROPIC_API_KEY=sk-ant-...

# Telegram Bot (from @BotFather on Telegram)
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...          # your personal chat ID

# Optional tuning
ALERT_SCORE_THRESHOLD=7       # minimum score to send alert (out of 10)
NSE_POLL_INTERVAL_SECONDS=300 # 5 minutes
NEWS_POLL_INTERVAL_SECONDS=900 # 15 minutes
REGULATORY_POLL_INTERVAL_SECONDS=3600 # 1 hour
```

---

## Deep Agents Architecture

**Do NOT use raw LangGraph `StateGraph` / `GraphState` / `Send` API directly.**
agentmesh uses the `deepagents` library, which is a higher-level harness built *on top of* LangGraph. You never write graph nodes or edges — the harness handles all of that.

The pattern is:
1. Write plain Python **tool functions** (NSE poller, RSS reader, Telegram sender, scorer)
2. Define **subagents as dicts** with `name`, `description`, `system_prompt`, `tools`
3. Call `create_deep_agent()` with tools + subagents — done

**Install:**
```bash
uv add deepagents langchain-anthropic
```

### Main agent structure

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    model="openai:gpt-4.1-mini",   # cheap model for orchestration
    system_prompt=ORCHESTRATOR_PROMPT,
    tools=[send_telegram_alert],                 # only tools the main agent needs directly
    subagents=[
        corporate_action_subagent,
        insider_activity_subagent,
        sector_catalyst_subagent,
        earnings_beat_subagent,
        scorer_subagent,
    ],
)

# Trigger a run (called by your scheduler)
result = agent.invoke({
    "messages": [{"role": "user", "content": "Scan for profitable market events now"}]
})
```

### Subagent definitions

Each subagent is a plain dict. The main agent calls them via the built-in `task()` tool.
Context isolation is automatic — subagent's raw tool outputs never clutter the main agent's context.

```python
# --- Data collection subagents ---

corporate_action_subagent = {
    "name": "corporate-action-agent",
    "description": (
        "Fetches and analyses NSE corporate announcements. Use when scanning "
        "for M&A, buybacks, demergers, or board meeting notices."
    ),
    "system_prompt": """You scan NSE corporate announcements for high-impact events.
Focus on: M&A, acquisitions, buybacks, demergers, fundraising board meetings.
Ignore: AGM notices, dividend declarations under 5%, routine updates.
Return a JSON list of events with fields: ticker, event_type, summary, raw_url.""",
    "tools": [fetch_nse_announcements],
    "model": "anthropic:claude-haiku-4-5-20251001",       # cheap — just fetching and filtering
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
    "model": "anthropic:claude-haiku-4-5-20251001",
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
    "tools": [fetch_google_news_rss, fetch_rbi_sebi_rss],
    "model": "anthropic:claude-haiku-4-5-20251001",
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
    "tools": [fetch_event_calendar, fetch_google_news_rss],
    "model": "anthropic:claude-haiku-4-5-20251001",
}

# --- Scoring subagent (uses claude-sonnet for quality reasoning) ---

scorer_subagent = {
    "name": "opportunity-scorer",
    "description": (
        "Scores a market event for profit potential. Use after collecting event data. "
        "Returns impact score 1-10, confidence, urgency, and alert text."
    ),
    "system_prompt": """You are a financial event scorer for an Indian retail stock trader.
Given a market event, score it:
- impact_score (1-10): likelihood of >5% price move
- confidence (high/medium/low): signal clarity
- urgency (act_today / this_week / monitor): time to act
- affected_ticker: NSE symbol
- expected_move_pct: e.g. '+8% to +15%'
- reasoning: 2-3 sentences
- historical_analogy: one comparable past event + outcome

Only recommend alerting if impact_score >= 7.
Respond ONLY in valid JSON. No preamble.""",
    "tools": [],                                 # pure reasoning, no tools needed
    "model": "anthropic:claude-sonnet-4-6",     # sonnet for quality scoring
}
```

### Orchestrator system prompt

```python
ORCHESTRATOR_PROMPT = """You are the agentmesh orchestrator — an Indian stock market alert system.

Your job every run:
1. Use write_todos to plan your scan
2. Delegate to corporate-action-agent, insider-activity-agent, sector-catalyst-agent,
   earnings-beat-agent (run all 4 via task() calls)
3. Pass collected events to opportunity-scorer
4. If any event scores >= 7, call send_telegram_alert with the formatted alert
5. If nothing scores >= 7, do nothing (no false alarms)

IMPORTANT: Always delegate to subagents using task(). Never do the data fetching yourself.
This keeps your context clean and ensures each agent focuses on its specialty.
"""
```

### Scheduler (main.py)

The agent is triggered on a schedule — not a continuous loop.

```python
from apscheduler.schedulers.blocking import BlockingScheduler
from agents.agentmesh import agent

def run_scan():
    agent.invoke({
        "messages": [{"role": "user", "content": "Scan for profitable market events now"}]
    })

scheduler = BlockingScheduler(timezone="Asia/Kolkata")
scheduler.add_job(run_scan, "cron", hour="9-16", minute="*/15")   # every 15 min, market hours
scheduler.add_job(run_scan, "cron", hour=18, minute=30)           # once at 6:30pm for bulk/block deals
scheduler.start()
```

### Backend — deduplication across runs

The default `StateBackend` is **ephemeral per thread** — files are lost when a run ends. To prevent re-alerting on the same event across multiple scheduled runs, use a `CompositeBackend` that persists seen-events to a `StoreBackend`:

```python
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.store.memory import InMemoryStore          # dev
# from langgraph.store.postgres import PostgresStore      # production

store = InMemoryStore()  # swap for PostgresStore in production

def make_backend(runtime):
    return CompositeBackend(
        default=StateBackend(runtime),          # ephemeral scratch space
        routes={
            "/memories/": StoreBackend(runtime) # persists across runs
        }
    )

agent = create_deep_agent(
    model="openai:gpt-4.1-mini",
    system_prompt=ORCHESTRATOR_PROMPT,
    tools=[send_telegram_alert],
    subagents=[...],
    backend=make_backend,
    store=store,
    checkpointer=MemorySaver(),
)
```

The orchestrator system prompt should instruct the agent to write seen event IDs to `/memories/seen_events.txt` and skip any event already listed there. This replaces ChromaDB entirely.

### Human-in-the-loop — NOT in v1

**Decision: Do not implement HITL in v1.**

Reasons:
- Every test run would block waiting for manual approval, making iteration slow
- The scorer's `impact_score >= 7` threshold is the real safety gate — if calibrated correctly, low-quality events never reach `send_telegram_alert`
- A Telegram message you ignore is zero-risk — it's not executing a trade
- HITL adds `interrupt_on` + `checkpointer` plumbing that complicates the codebase before the system is even proven to work

**Use DRY_RUN mode instead for safe testing in v1:**

```python
# .env
DRY_RUN=true   # set to false when ready for live alerts

# delivery/telegram_bot.py
def send_telegram_alert(message: str) -> str:
    """Send a stock market alert to Telegram."""
    if config.DRY_RUN:
        print(f"\n[DRY RUN] Alert suppressed — would have sent:\n{message}\n")
        return "dry_run"
    # ... actual python-telegram-bot send logic
```

This gives full visibility during development with zero friction. Flip `DRY_RUN=false` in `.env` when you're confident in the scorer's quality.

**Add HITL in v2** once the system is working and you want a deliberate approval gate before alerts fire. The pattern when you're ready:
```python
# v2 only — do not implement in v1
agent = create_deep_agent(
    ...
    interrupt_on={"send_telegram_alert": True},
    checkpointer=MemorySaver(),
)
```

### Streaming — monitor subagent progress in logs

Instead of `agent.invoke()`, use `agent.stream()` to see live subagent activity in your terminal:

```python
for chunk in agent.stream(
    {"messages": [{"role": "user", "content": "Scan for profitable market events now"}]},
    stream_mode="updates",
    subgraphs=True,       # receive events from inside subagents
    version="v2",
):
    if chunk["type"] == "updates":
        source = f"[subagent {chunk['ns']}]" if chunk["ns"] else "[main agent]"
        for node, data in chunk["data"].items():
            print(f"{source} → {node}")
```

This is very useful during development to see which subagent is running, what it found, and when the scorer fires.

---



### Key Deep Agents concepts used in agentmesh

| Concept | What it does | Where used |
|---|---|---|
| `create_deep_agent()` | Creates the orchestrator with harness | `agents/agentmesh.py` |
| `subagents` param | Registers specialist agents | All 5 subagents |
| `task()` tool (built-in) | Orchestrator calls subagents | Auto-provided by harness |
| `write_todos` (built-in) | Agent plans its scan steps | Orchestrator |
| `model="openai:X"` | Provider-prefixed model strings | All agents |
| Context isolation | Subagent outputs don't bloat main context | Automatic |
| `model` per subagent | Haiku for cheap fetching, Sonnet for scoring | Saves cost |
| `CompositeBackend` | Routes `/memories/` to persistent store | Deduplication |
| `StoreBackend` | Cross-run persistence for seen events | `/memories/seen_events.txt` |
| `interrupt_on` | Pause before sending alert for approval | Optional HITL gate |
| `checkpointer` | Required when using HITL | `MemorySaver()` in dev |
| `agent.stream(..., subgraphs=True)` | Live subagent progress in logs | Development/debugging |

---

## Build Order (recommended sequence)

1. **`sources/nse.py`** — `fetch_nse_announcements()` tool function with session headers
2. **`delivery/telegram_bot.py`** — `send_telegram_alert()` tool function, test with hardcoded message
3. **`agents/subagents/scorer.py`** — scorer subagent dict (no tools, just the prompt)
4. **`agents/agentmesh.py`** — wire together with `create_deep_agent()`, test end-to-end with just NSE + scorer + Telegram
5. **`sources/deals.py`** — bulk/block deals fetcher
6. **`sources/news_rss.py`** — Google News + RBI + SEBI RSS
7. **Remaining subagent dicts** — insider_activity, sector_catalyst, earnings_beat
8. **`main.py`** — APScheduler with market hours cron

Test each step independently before moving to the next.

---

## Key Decisions Already Made

- **Deep Agents (`deepagents` library)** — harness built on LangGraph. Use `create_deep_agent()` + subagent dicts. Do NOT use raw `StateGraph` / `GraphState` / `Send` API
- **Subagents as dicts** — `name`, `description`, `system_prompt`, `tools`, optional `model`
- **Model format** — always use provider-prefixed strings, e.g. `"openai:gpt-4.1-mini"` or `"anthropic:claude-sonnet-4-6"`. Never bare model names
- **Model tiering** — orchestrator uses `"openai:gpt-5-mini"` (reliable agentic stop behavior, ~55s per scan), all subagents use `"openai:gpt-4.1-mini"` (cheap single-step tool calls), scorer uses `"openai:gpt-4.1-mini"`. `recursion_limit=50` enforced as hard safety net. `gpt-4.1-mini` was tested as orchestrator and rejected — loops indefinitely
- **Deduplication via CompositeBackend** — use `CompositeBackend` with `StoreBackend` routing `/memories/` for cross-run persistence. Orchestrator writes seen event IDs to `/memories/seen_events.txt`. ChromaDB not needed
- **No automated trading** — system alerts only, human makes all buy/sell decisions
- **Free tier first** — upgrade to Kite Connect (₹2k/month) only after v1 is working
- **Telegram over WhatsApp** — simpler API, no approval process, instant delivery
- **No HITL in v1** — use `DRY_RUN=true` in `.env` instead for safe testing. HITL (`interrupt_on` + `checkpointer`) is a v2 feature once the system is proven. The `impact_score >= 7` gate is the real safety net
- **Streaming for debugging** — use `agent.stream(..., subgraphs=True, version="v2")` during development to see live subagent activity
- **Indian market focus** — NSE primary. Nifty 50 + Nifty Next 50 universe to start

---

## Notes for Claude Code

- Always activate the venv before running: `source agentmesh/.venv/bin/activate` — or just prefix commands with `uv run`
- To add a new package: `uv add <package>` (not pip install)
- To run a script: `uv run python main.py` or `uv run pytest`
- NSE endpoints are brittle — wrap all calls in try/except with exponential backoff
- Never commit `.env` to git — add it to `.gitignore` immediately
- Model strings MUST use provider prefix: `"anthropic:claude-haiku-4-5-20251001"` not `"claude-haiku-4-5-20251001"`
- Always start with `DRY_RUN=true` in `.env` — flip to `false` only when scorer quality is confirmed. Do NOT implement `interrupt_on` HITL in v1
- The `ANTHROPIC_API_KEY` env var must be set — `deepagents` and `langchain-anthropic` pick it up automatically. Do NOT hardcode it
- For cross-run deduplication, the agent writes to `/memories/seen_events.txt` via `CompositeBackend` + `StoreBackend`
- Use `agent.stream(..., subgraphs=True, version="v2")` instead of `agent.invoke()` during dev to see subagent activity
- Target Python 3.11+
