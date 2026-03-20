# agentmesh

An AI-powered multi-agent stock market alert system for Indian markets (NSE/BSE) that monitors corporate events, bulk deals, institutional flows, news, and earnings — and sends actionable alerts to Telegram when profitable opportunities are detected.

> Core pipeline is working. 5 parallel subagents including FII/DII flow monitoring, live price context in every alert, and market holiday awareness.

---

## What it does

agentmesh runs a mesh of specialised AI agents on a schedule during market hours. Each agent focuses on one type of signal. A scoring agent rates every event for profit potential, enriches it with live price context, and adjusts for institutional sentiment. If something scores 7/10 or higher, you get a Telegram message with the full context.

**Events it detects:**
- M&A announcements, buybacks, demergers, board meetings with fundraising agenda
- Promoter bulk buying / institutional accumulation / large block deals
- Government contracts, PLI scheme approvals, defence and railway orders
- Earnings surprises — beats or misses vs analyst estimates
- RBI/SEBI policy announcements that could affect specific sectors
- FII/DII institutional flow — net buy/sell sentiment across the market

**Score calibration:**
- FII/DII flows from the macro-context agent act as a sentiment modifier — bearish FII days reduce all scores by 1 point
- Market holiday awareness — `act_today` urgency automatically shifts to `this_week` on NSE holidays

**Who it's for:** Retail investors who want AI-assisted market monitoring without paying for expensive data terminals. You make all trading decisions — agentmesh is a research and signal copilot.

---

## Architecture

The orchestrator delegates to five data-collection subagents in parallel, passes their combined output to a scorer, and fires a Telegram alert only when the score clears the threshold.

```
┌─────────────────────────────────────────────────────────────┐
│                        Orchestrator                         │
│                gpt-5-mini — plans & routes                  │
└──────┬────────┬──────────┬───────────┬──────────────────────┘
       │        │          │           │           │
┌──────▼─┐ ┌───▼────┐ ┌───▼─────┐ ┌──▼──────┐ ┌──▼──────────┐
│Corp.   │ │Insider │ │ Sector  │ │Earnings │ │   Macro     │
│Action  │ │Activity│ │Catalyst │ │  Beat   │ │  Context    │
└──────┬─┘ └───┬────┘ └───┬─────┘ └──┬──────┘ └──┬──────────┘
       └───────┴──────────┴───────────┴────────────┘
                                │
                     ┌──────────▼──────────┐
                     │  Opportunity Scorer │
                     │  + yfinance price   │
                     └──────────┬──────────┘
                                │
                     ┌──────────▼──────────┐
                     │   Telegram Alert    │
                     └─────────────────────┘
```

**Subagents:**

| Subagent | Data Source | Purpose |
|---|---|---|
| corporate-action-agent | NSE announcements API | M&A, buybacks, demergers |
| insider-activity-agent | NSE bulk + block deals | Institutional and promoter buying |
| sector-catalyst-agent | Google News RSS | Policy, contracts, sector news |
| earnings-beat-agent | NSE event calendar + Google News | Results, earnings surprises |
| macro-context-agent | NSE FII/DII API | Institutional flow sentiment |
| opportunity-scorer | All of the above + yfinance | Scores, ranks, enriches with price |

Built on [Deep Agents](https://github.com/langchain-ai/deepagents) — a higher-level harness on top of LangGraph. The orchestrator uses `gpt-5-mini` for reliable agentic stop behaviour. All data-collection subagents use `gpt-4.1-mini` (cheap, single-step tool calls).

---

## Data sources

| Source | What it provides | Polling schedule |
|---|---|---|
| NSE corporate announcements | Board meetings, M&A, buybacks, demergers | Every 15 min, 9am–4pm IST |
| NSE bulk deals | Large single-session trades (>0.5% equity) | Once daily at 6:30pm IST |
| NSE block deals | Pre-negotiated large block transactions | Once daily at 6:30pm IST |
| NSE FII/DII trade data | Daily institutional net buy/sell flows (fiidiiTradeReact endpoint) | Once daily at 6:30pm IST |
| yfinance | Live price, % change today, 52W high/low, market cap | Per alert, at scoring time |
| NSE event calendar | Upcoming results dates, board meetings, dividends | Once daily at 8am IST |
| NSE holiday master | 20 trading holidays for 2026 | Loaded at startup |
| Google News RSS | Market news, sector developments, company news | Per subagent invocation |
| RBI RSS | Press releases and notifications | Per subagent invocation |
| SEBI RSS | Circulars, policy changes (enforcement noise filtered) | Per subagent invocation |

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
uv run python sources/fii_dii.py
uv run python sources/price.py

# Integration tests
uv run python tests/test_integration.py
```

**Schedule:**
- Mon–Fri 9:00am–4:00pm IST — every 15 minutes (corporate announcements, news)
- Mon–Fri 6:30pm IST — daily run for bulk/block deals and FII/DII data (published after market close)

---

## Docker *(next session)*

Docker + Raspberry Pi deployment coming in the next session.
The system is designed to run unattended 24/7 on a Raspberry Pi with `docker compose up -d`.

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
│   ├── events.py              ← NSE results/earnings calendar
│   ├── fii_dii.py             ← NSE FII/DII institutional flow data
│   └── price.py               ← yfinance live price, 52W range, market cap
│
├── delivery/
│   └── telegram_bot.py        ← send_telegram_alert tool function
│
├── utils/
│   ├── config.py              ← loads .env, exposes settings
│   ├── logger.py              ← logging setup
│   └── market_calendar.py     ← NSE trading holiday master for 2026
│
└── tests/
    └── test_integration.py    ← end-to-end integration tests
```

---

## Alert format

Alerts follow a fixed structure so they're scannable at a glance:

```
🚨 ALERT — High Confidence

Stock:          UNOMINDA.NS
Price:          ₹1067.0 (+2.65% today) | 52W: ₹767.6–₹1382.0 | 22.8% from 52W high | Mkt Cap: ₹61610 Cr
Event:          Block deal purchase by promoter group (1,410,000 shares at ₹1100 each)
Impact Score:   8/10
Urgency:        act_today
Expected Move:  +5% to +10%

Reasoning: Large block purchase of ₹155.1 crore by promoter group signals
strong confidence in the stock. The size and promoter involvement imply a
bullish catalyst notwithstanding FII selling.
Analogy: Similar to when promoter buying in Minda Industries in 2022 led
to a 12% rally in weeks.
FII Today: FII net sold ₹5,518 Cr today — institutional selling reduces
confidence in bullish alerts

Source: https://www.nseindia.com/market-data/block-deals
```

Only events scoring **7/10 or above** trigger an alert. The scorer filters out noise so you only see high-conviction signals.

---

## Scoring system

| Score | Meaning | Frequency |
|---|---|---|
| 9–10 | Extraordinary — transformative M&A, massive institutional buy >1% market cap | At most once a week |
| 7–8 | High impact — promoter buying, large block deals >₹100 Cr, contract wins | 2–3 times a week |
| 5–6 | Moderate — worth monitoring, not alerted | Daily |
| 1–4 | Noise — AGMs, routine filings | Excluded |

**FII modifier:** bearish FII day (net sell >₹500 Cr) reduces all scores by 1 point.

**Holiday modifier:** `act_today` urgency changes to `this_week` on NSE holidays.

---

## Disclaimer

agentmesh is not financial advice. It is a research and monitoring tool that surfaces publicly available market data. All buy and sell decisions are made by you. Past analogies referenced in alerts do not guarantee future performance. Use at your own risk.

---

## License

MIT
