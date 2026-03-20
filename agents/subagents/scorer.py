from sources.price import fetch_stock_context

scorer_subagent = {
    "name": "opportunity-scorer",
    "description": (
        "Scores a market event for profit potential. Use after collecting event data. "
        "Returns impact score 1-10, confidence, urgency, and alert text."
    ),
    "system_prompt": """You are a financial event scorer for a retail investor in Indian equities.

You receive a LIST of market events plus FII/DII macro context.
Score ALL events in one response.

SCORING CALIBRATION — be strict:
9-10: Extraordinary. Transformative M&A, massive institutional buy (>1% of market cap),
      earnings beat >50% above estimates. Should fire at most once a week.
7-8:  High impact. Clear positive catalyst with strong evidence.
      Promoter buying, large block deals (>₹100 Cr), contract wins >5x quarterly revenue,
      results beat >20% above estimates. Should fire 2-3 times per week.
5-6:  Moderate. Worth monitoring. Bulk deals, smaller contract wins, inline results.
      Do not alert — return for context only.
1-4:  Noise. AGMs, routine filings, small deals. Exclude entirely.

FII/DII MODIFIER:
- If FII sentiment is bearish: reduce score by 1 on all bullish signals
- If FII sentiment is bullish: increase score by 1 (max 10)
- If FII data unavailable: no adjustment

MARKET HOLIDAY MODIFIER:
- If today is a market holiday: change urgency from act_today → this_week

For each event with score >= 5:
1. Call fetch_stock_context(ticker) to get live price and 52W range
2. Include the price summary in your output as price_context

Return a JSON ARRAY sorted by impact_score descending.
Only include events with final score >= 7.

Fields per event:
  impact_score, confidence, urgency, affected_ticker,
  expected_move_pct, reasoning, historical_analogy,
  price_context (from fetch_stock_context summary field, or "" if unavailable),
  fii_context (from the FII/DII context passed in)

Respond ONLY in valid JSON array. No preamble. No markdown.""",
    "tools": [fetch_stock_context],
    "model": "openai:gpt-4.1-mini",
}


def make_scorer_agent():
    from deepagents import create_deep_agent
    return create_deep_agent(
        model="openai:gpt-4.1-mini",
        system_prompt=(
            "You are a market event router. Your ONLY job is to delegate scoring "
            "tasks to the opportunity-scorer subagent using the task() tool, then "
            "return its response EXACTLY as-is — raw JSON, no rephrasing, no "
            "summary, no explanation. Do not modify the subagent output in any way."
        ),
        tools=[],
        subagents=[scorer_subagent],
        name="agentmesh-orchestrator",
    )


if __name__ == "__main__":
    import utils.config  # loads .env and OPENAI_API_KEY into os.environ

    agent = make_scorer_agent()

    result = agent.invoke({
        "messages": [{
            "role": "user",
            "content": (
                "Score this event: BEML has been awarded a ₹3,200 crore "
                "railway contract by the Ministry of Railways for "
                "manufacturing metro coaches."
            )
        }]
    })

    last_msg = result["messages"][-1]
    content = last_msg.content
    if isinstance(content, list):
        content = " ".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    print(content)

