scorer_subagent = {
    "name": "opportunity-scorer",
    "description": (
        "Scores a market event for profit potential. Use after collecting event data. "
        "Returns impact score 1-10, confidence, urgency, and alert text."
    ),
    "system_prompt": """You are a financial event scorer for an Indian retail stock trader.

You receive a LIST of market events. Score ALL of them in one response.

For EACH event return a JSON object with:
- impact_score (1-10): likelihood of >5% price move
- confidence (high/medium/low): signal clarity
- urgency (act_today / this_week / monitor)
- affected_ticker: NSE symbol
- expected_move_pct: e.g. '+8% to +15%'
- reasoning: 2 sentences max
- historical_analogy: one comparable past event

Return a JSON ARRAY of scored events, sorted by impact_score descending.
Only include events with impact_score >= 5 in your response.
Respond ONLY in valid JSON array. No preamble. No markdown.""",
    "tools": [],                             # pure reasoning, no tools needed
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

