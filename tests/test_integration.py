import utils.config  # loads .env — must be first so all API keys hit os.environ

from sources.nse import fetch_nse_announcements
from agents.subagents.scorer import make_scorer_agent
from delivery.telegram_bot import send_telegram_alert

assert not utils.config.DRY_RUN, (
    "ABORT: DRY_RUN is true in .env — set DRY_RUN=false to send a real Telegram message."
)

try:
    # ------------------------------------------------------------------
    # STEP 1: NSE
    # ------------------------------------------------------------------
    announcements = fetch_nse_announcements()
    assert isinstance(announcements, list), "NSE: expected a list"
    assert len(announcements) > 0, "NSE: got empty list — check session headers"
    for item in announcements:
        for key in ("symbol", "subject", "date", "description", "url"):
            assert key in item, f"NSE: missing key '{key}' in {item}"
    print(f"✓ NSE:      fetched {len(announcements)} announcements")
    print(f"            first → {announcements[0]['symbol']} | {announcements[0]['subject'][:60]}")

    # ------------------------------------------------------------------
    # STEP 2: SCORER
    # ------------------------------------------------------------------
    agent = make_scorer_agent()

    first = announcements[0]
    message = (
        f"Score this event: {first['symbol']} — {first['subject']}. "
        f"Details: {first['description'][:200]}"
    )

    result = agent.invoke({"messages": [{"role": "user", "content": message}]})

    raw = result["messages"][-1].content
    if isinstance(raw, list):
        raw = " ".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in raw
        )

    assert "impact_score" in raw, f"Scorer: expected impact_score in output, got: {raw[:200]}"
    import json
    print(f"✓ Scorer:   analysis complete")
    print(f"\n{'='*50}")
    print("SCORER OUTPUT:")
    print(f"{'='*50}")
    try:
        # Try to pretty-print as JSON
        parsed = json.loads(raw)
        print(json.dumps(parsed, indent=2))
    except json.JSONDecodeError:
        # If not pure JSON, print raw (orchestrator may have wrapped it)
        print(raw)
    print(f"{'='*50}\n")

    # ------------------------------------------------------------------
    # STEP 3: TELEGRAM
    # ------------------------------------------------------------------
    try:
        parsed_score = json.loads(raw)
        alert_msg = (
            f"agentmesh integration test ✓\n\n"
            f"Stock: {parsed_score.get('affected_ticker', 'N/A')}\n"
            f"Impact Score: {parsed_score.get('impact_score', 'N/A')}/10\n"
            f"Confidence: {parsed_score.get('confidence', 'N/A')}\n"
            f"Urgency: {parsed_score.get('urgency', 'N/A')}\n"
            f"Expected Move: {parsed_score.get('expected_move_pct', 'N/A')}\n\n"
            f"Reasoning: {parsed_score.get('reasoning', 'N/A')}"
        )
    except json.JSONDecodeError:
        alert_msg = f"agentmesh integration test ✓\n\nScorer output:\n{raw}"

    status = send_telegram_alert(alert_msg)
    assert status == "sent", (
        f"Telegram: expected 'sent', got '{status}'"
    )
    print(f"✓ Telegram: message sent successfully")

    # ------------------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------------------
    print("\n=== Integration test passed ✓ ===")
    print(f"  NSE      → {len(announcements)} announcements fetched")
    print(f"  Scorer   → impact_score confirmed in JSON output")
    print(f"  Telegram → message sent to chat")

except AssertionError as exc:
    print(f"\n✗ FAILED: {exc}")
    raise SystemExit(1)
except Exception as exc:
    print(f"\n✗ ERROR: {type(exc).__name__}: {exc}")
    raise SystemExit(1)
