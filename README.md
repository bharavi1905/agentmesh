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
- Screener.in fundamentals — ROCE, ROE, revenue growth, D/E, promoter holding, P/E for every alerted stock
- NSE EQUITY_L.csv validation — all tickers validated against 2000+ NSE-listed symbols before processing
- Two-pass scoring — batch pre-filter then individual deep scoring per candidate event

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
| insider-activity-agent | NSE bulk + block deals | Promoter/institutional buying |
| sector-catalyst-agent | Google News RSS | Defence contracts, railway orders, PLI |
| earnings-beat-agent | NSE event calendar + Google News | Results, earnings surprises |
| macro-context-agent | NSE FII/DII API | Institutional flow sentiment |
| opportunity-scorer | All above + yfinance + Screener.in | Two-pass scoring + narratives |

Built on [Deep Agents](https://github.com/langchain-ai/deepagents) — a higher-level harness on top of LangGraph. The orchestrator uses `gpt-5-mini` for reliable agentic stop behaviour. All data-collection subagents use `gpt-4.1-mini` (cheap, single-step tool calls).

**Two-pass scoring:**
1. Batch pre-filter — all events scored quickly to identify candidates >= 6
2. Individual deep scoring — each candidate scored separately with full enrichment: live price, 52W range, market cap, and 5-dimension business quality narrative (ROCE, ROE, growth, D/E, promoter holding, P/E)

**Ticker validation:**
All tickers from subagents are validated against NSE's official EQUITY_L.csv (2000+ symbols, cached 7 days). Invalid, hallucinated, or generic tickers (PSU, INFRA, METAL etc.) are silently discarded before any enrichment calls.

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
| Screener.in | Business quality fundamentals per stock | Per alert, at scoring time |
| NSE EQUITY_L.csv | Complete list of 2000+ NSE-listed symbols | Cached 7 days, auto-refreshed |

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
│   ├── agentmesh.py           ← orchestrator, 5 subagents, two-pass scoring
│   └── subagents/
│       └── scorer.py          ← two-pass scorer with Business Quality narratives
│
├── sources/
│   ├── nse.py                 ← NSE corporate announcements
│   ├── deals.py               ← NSE bulk deals + block deals
│   ├── news_rss.py            ← Google News, RBI, SEBI RSS (recency filtered)
│   ├── events.py              ← NSE earnings/results calendar
│   ├── fii_dii.py             ← NSE FII/DII institutional flow data
│   ├── price.py               ← yfinance live price, 52W range, market cap
│   └── fundamentals.py        ← Screener.in scraper + smart slug resolver
│
├── delivery/
│   └── telegram_bot.py        ← HTML-formatted Telegram alerts with sanitiser
│
├── utils/
│   ├── config.py              ← all API endpoints centralised
│   ├── enrichment.py          ← parallel prefetch coordinator (price + fundamentals)
│   ├── market_calendar.py     ← NSE holiday awareness (20 holidays for 2026)
│   └── nse_symbols.py         ← NSE equity list validator (EQUITY_L.csv)
│
├── data/
│   └── nse_equity.csv         ← cached NSE symbol list (auto-refreshed, gitignored)
│
└── tests/
    └── test_integration.py
```

---

## Alert format

Alerts follow a fixed structure so they're scannable at a glance:

```
🚨 ALERT — High Confidence

Stock:          BEL
Price:          ₹426.1 (-1.09% today) | 52W: ₹256.2–₹473.45 | 10.0% from 52W high | Mkt Cap: ₹311470 Cr
Event:          BEL Bags ₹1,011 Crore Orders; shares gained 1.46%
Impact Score:   8/10  (raw 8, FII -1, fundamentals +1)
Urgency:        act_today
Expected Move:  5-10%

Reasoning: BEL won ₹1,011 Crore defence orders — a material contract that
adds to near-term revenue and backlog. Heavy FII selling today reduces
immediate confidence (FII adj -1) though strong fundamentals warrant
positive bias (+1). Watch order execution details for confirmation.
Analogy:   Comparable to past large order wins by defence PSUs that drove
multi-week re-ratings once execution clarity emerged.
FII Today: FII net sold ₹5,518 Cr today — institutional selling reduces
confidence in bullish alerts

── Business Quality ──
- Growth: 16% revenue CAGR (3yr) — Steady mid-teens growth for a defence electronics leader
- Profitability: ROCE 38.9%, ROE 29.2% — Very strong; well above cost of capital
- Financial Health: D/E 0.00 — Zero debt; balance sheet can support large contract execution without financial strain
- Promoter Conviction: 51.14% promoter holding — Majority state ownership provides stable long-term stewardship
- Valuation: P/E 52.2x — Rich but justified by high returns; limited margin for disappointment

Source:  View article
Verify:  https://www.screener.in/company/BEL/consolidated/
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

**Fundamentals modifier:** strong business (ROCE >15%, growth >15%, promoter >50%) → +1 to score. Weak business (ROCE <8%, growth <8%, promoter <35%) → -1 to score. Both modifiers can stack with FII modifier.

**Holiday modifier:** `act_today` urgency changes to `this_week` on NSE holidays.

**Transparent scoring:** every alert shows the full modifier breakdown, e.g. `8/10 (raw 8, FII -1, fundamentals +1)` so you know exactly why a score changed.

---

## Known limitations

- **Source URL display** — Google News alert source URLs are long redirect URLs. They work when tapped but display as "View article" to keep the alert readable. A cleaner solution is planned.
- **Memory resets on restart** — deduplication uses InMemoryStore which resets when the process restarts. Production deployment on Raspberry Pi will use file-based persistence.
- **yfinance rate limiting** — Yahoo Finance may rate-limit on very high-frequency scans. The system degrades gracefully — price shows as "unavailable" rather than breaking the alert.
- **Screener.in rate limiting** — fetching fundamentals for >10 stocks per scan can trigger 429 responses. Handled with 500ms stagger and exponential backoff retry.

---

## Disclaimer

agentmesh is not financial advice. It is a research and monitoring tool that surfaces publicly available market data. All buy and sell decisions are made by you. Past analogies referenced in alerts do not guarantee future performance. Use at your own risk.

---

## License

MIT
