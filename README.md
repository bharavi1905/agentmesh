# agentmesh

An AI-powered multi-agent stock market alert system for Indian markets (NSE/BSE) that monitors corporate events, bulk deals, news, and earnings — and sends actionable alerts to Telegram when profitable opportunities are detected.

> v1 — core pipeline is working. Some subagents are still being expanded with more data sources. Docker deployment is in progress.

---

## What it does

agentmesh runs a mesh of specialised AI agents on a schedule during market hours. Each agent focuses on one type of signal, and a scoring agent rates every event for profit potential. If something scores 7/10 or higher, you get a Telegram message with the full context.

**Events it detects:**
- M&A announcements, buybacks, demergers, board meetings with fundraising agenda
- Promoter bulk buying / institutional accumulation / large block deals
- Government contracts, PLI scheme approvals, defence and railway orders
- Earnings surprises — beats or misses vs analyst estimates
- RBI/SEBI policy announcements that could affect specific sectors

**Example alert:**

```
🚨 ALERT — High Confidence

Stock:         JPPOWER.NS
Event:         JUMP TRADING FINANCIAL INDIA PRIVATE LIMITED bought
               50,388,956 shares in a bulk deal
Impact Score:  9/10
Urgency:       act_today
Expected Move: +7% to +12%

Reasoning: Large share purchase by a known trading entity signals
strong bullish sentiment and potential positive re-rating.
Analogy: Similar to large bulk buys in Tata Motors in 2023, which
preceded a 10% price rally within days.

Source: https://www.nseindia.com/market-data/bulk-deals
```

**Who it's for:** Retail investors who want AI-assisted market monitoring without paying for expensive data terminals. You make all trading decisions — agentmesh is a research and signal copilot.

---

## Architecture

The system is a hierarchy of agents. The orchestrator delegates to four data-collection subagents in parallel, passes their combined output to a scorer, and fires a Telegram alert only when the score clears the threshold.

```
┌─────────────────────────────────────────────────────┐
│                    Orchestrator                     │
│              gpt-5-mini — plans & routes            │
└───────────┬─────────┬──────────┬──────────┬─────────┘
            │         │          │          │
    ┌───────▼──┐ ┌────▼────┐ ┌──▼──────┐ ┌─▼────────┐
    │Corporate │ │ Insider │ │ Sector  │ │ Earnings │
    │ Action   │ │Activity │ │Catalyst │ │  Beat    │
    └───────┬──┘ └────┬────┘ └──┬──────┘ └─┬────────┘
            └─────────┴─────────┴───────────┘
                              │
                   ┌──────────▼──────────┐
                   │  Opportunity Scorer │
                   │  gpt-4.1-mini       │
                   └──────────┬──────────┘
                              │
                   ┌──────────▼──────────┐
                   │   Telegram Alert    │
                   └─────────────────────┘
```

**Subagents:**

| Subagent | Role | Data sources |
|---|---|---|
| corporate-action-agent | M&A, buybacks, demergers, board meetings | NSE corporate announcements API |
| insider-activity-agent | Bulk deals, block deals, promoter trades | NSE snapshot-capital-market-largedeal API |
| sector-catalyst-agent | Govt contracts, PLI, policy news | Google News RSS, RBI RSS, SEBI RSS |
| earnings-beat-agent | Earnings surprises vs estimates | NSE event calendar, Google News RSS |
| opportunity-scorer | Rates each event 1–10 for profit potential | Pure LLM reasoning, no tools |

Built on [Deep Agents](https://github.com/langchain-ai/deepagents) — a higher-level harness on top of LangGraph. The orchestrator uses `gpt-5-mini` for reliable agentic stop behaviour. All data-collection subagents use `gpt-4.1-mini` (cheap, single-step tool calls).

---

## Data sources

| Source | What it provides | Polling schedule |
|---|---|---|
| NSE corporate announcements | Board meetings, M&A, buybacks, demergers | Every 15 min, 9am–4pm IST |
| NSE bulk deals | Large single-session trades (>0.5% equity) | Once daily at 6:30pm IST |
| NSE block deals | Pre-negotiated large block transactions | Once daily at 6:30pm IST |
| Google News RSS | Market news, sector developments, company news | Per subagent invocation |
| RBI RSS | Press releases and notifications | Per subagent invocation |
| SEBI RSS | Circulars, policy changes (enforcement noise filtered) | Per subagent invocation |
| NSE event calendar | Upcoming results dates, board meetings, dividends | Once daily at 8am IST |

All NSE endpoints require a browser-like `requests.Session` with cookies — handled internally.

---

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- OpenAI API key — [platform.openai.com](https://platform.openai.com)
- Anthropic API key (optional, if switching to Claude models) — [console.anthropic.com](https://console.anthropic.com)
- Telegram bot token + your chat ID — create a bot via [@BotFather](https://t.me/BotFather)

---

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/yourname/agentmesh
cd agentmesh

# 2. Install dependencies
uv sync

# 3. Configure environment
cp .env.example .env
# Edit .env and fill in your API keys

# 4. Test run (fires once and exits)
uv run python main.py --now

# 5. Start scheduled mode
uv run python main.py
```

---

## Environment variables

| Variable | Required | Description | Example |
|---|---|---|---|
| `OPENAI_API_KEY` | Yes | OpenAI API key for gpt-5-mini / gpt-4.1-mini | `sk-proj-...` |
| `ANTHROPIC_API_KEY` | No | Anthropic API key (only if using Claude models) | `sk-ant-...` |
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from @BotFather | `7123456789:AAF...` |
| `TELEGRAM_CHAT_ID` | Yes | Your personal Telegram chat ID | `123456789` |
| `DRY_RUN` | No | `true` suppresses actual Telegram sends (default: `true`) | `false` |
| `ALERT_SCORE_THRESHOLD` | No | Minimum score to trigger an alert (default: `7`) | `7` |

Start with `DRY_RUN=true` until you're confident in the scorer's output quality. Flip to `false` when ready for live alerts.

---

## Running

```bash
# Scheduled mode — runs on market hours cron, stays alive
uv run python main.py

# Test mode — runs one scan immediately and exits
uv run python main.py --now

# Test individual data sources
uv run python sources/nse.py
uv run python sources/deals.py
uv run python sources/news_rss.py
uv run python sources/events.py

# Integration tests
uv run python tests/test_integration.py
```

**Schedule:**
- Mon–Fri 9:00am–4:00pm IST — every 15 minutes (corporate announcements, news)
- Mon–Fri 6:30pm IST — daily run for bulk/block deals (published after market close)

---

## Docker *(coming soon)*

Docker + Raspberry Pi deployment is in progress. The goal is an always-on low-power deployment that runs the scheduler 24/7 without needing a laptop awake.

---

## Project structure

```
agentmesh/
├── CLAUDE.md                  ← project context and architecture decisions
├── .env                       ← API keys (never commit)
├── .env.example               ← template for .env
├── pyproject.toml             ← dependencies managed by uv
├── uv.lock                    ← lockfile, committed to git
├── main.py                    ← entry point, starts APScheduler
│
├── agents/
│   ├── agentmesh.py           ← create_deep_agent() call, all subagent wiring
│   └── subagents/
│       └── scorer.py          ← opportunity-scorer subagent dict + test harness
│
├── sources/
│   ├── nse.py                 ← NSE corporate announcements poller
│   ├── deals.py               ← NSE bulk deals + block deals
│   ├── news_rss.py            ← Google News RSS, RBI RSS, SEBI RSS
│   └── events.py              ← NSE results/earnings calendar
│
├── delivery/
│   └── telegram_bot.py        ← send_telegram_alert tool function
│
├── utils/
│   ├── config.py              ← loads .env, exposes settings
│   └── logger.py              ← logging setup
│
└── tests/
    └── test_integration.py    ← end-to-end integration tests
```

---

## Alert format

Alerts follow a fixed structure so they're scannable at a glance:

```
🚨 ALERT — High Confidence

Stock:         JPPOWER.NS
Event:         JUMP TRADING FINANCIAL INDIA PRIVATE LIMITED bought
               50,388,956 shares in a bulk deal
Impact Score:  9/10
Urgency:       act_today
Expected Move: +7% to +12%

Reasoning: Large share purchase by a known trading entity signals
strong bullish sentiment and potential positive re-rating.
Analogy: Similar to large bulk buys in Tata Motors in 2023, which
preceded a 10% price rally within days.

Source: https://www.nseindia.com/market-data/bulk-deals
```

Only events scoring **7/10 or above** trigger an alert. The scorer filters out noise so you only see high-conviction signals.

---

## Disclaimer

agentmesh is not financial advice. It is a research and monitoring tool that surfaces publicly available market data. All buy and sell decisions are made by you. Past analogies referenced in alerts do not guarantee future performance. Use at your own risk.

---

## License

MIT
