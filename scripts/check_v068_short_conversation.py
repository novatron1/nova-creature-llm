from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v068_short_conversation import (
    is_short_mode, summarize_response,
    process_short_message, get_recent_short, get_summary,
)

ERRORS = []
PASSES = []

def check(cond, msg):
    PASSES.append(f"  {'✅' if cond else '❌'} {msg}")
    if not cond:
        ERRORS.append(msg)

def main():
    print("Nova Creature v068 — Short Conversation Checker\n")

    for f in [ROOT/"src"/"v068_short_conversation.py"]:
        check(f.exists(), f"{f.relative_to(ROOT)} exists")

    # Short mode detection
    check(is_short_mode("ok"), "single word detected as short")
    check(is_short_mode("do that"), "follow-up detected as short")
    check(is_short_mode("Who created you?"), "short question detected")
    check(not is_short_mode("This is a very long message that should not be short mode"), "long message not short")

    # Summarization
    short = summarize_response("Planner: keep the working stack as gold, add the next module in an experiment", max_len=30)
    check(len(short) <= 33, f"summarized to {len(short)} chars")

    # Process
    event = process_short_message("ok go", answer="Let's continue with the build.", route="planner")
    check(event["is_short_mode"], "ok go detected as short")
    check(event["short_answer"] is not None, "short_answer exists")

    # Log
    log = get_recent_short()
    check(len(log) >= 1, "log has entries")

    # Summary
    s = get_summary()
    check(s["short_mode_events"] >= 1, "summary has short mode events")

    print(f"\n{'='*60}")
    print(f"RESULTS: {len(PASSES)} passed, {len(ERRORS)} errors")
    print(f"{'='*60}")
    for p in PASSES:
        print(p)
    for e in ERRORS:
        print(f"  ❌ {e}")

    return 0 if not ERRORS else 1

if __name__ == "__main__":
    raise SystemExit(main())
