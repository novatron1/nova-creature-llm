#!/usr/bin/env python3
"""Check v062 growth engine installation and operation."""

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v062_growth_streams import list_streams, get_trainable_streams, get_streams_requiring_approval
from v062_growth_engine import capture_growth_event, get_all_counts

ERRORS = []
PASSES = []

def check(cond, msg):
    if cond:
        PASSES.append(f"  ✅ {msg}")
    else:
        ERRORS.append(f"  ❌ {msg}")

def main():
    print("Nova Creature v062 — Growth Engine Checker\n")

    # 1. Files exist
    print("1. Checking source files…")
    for f in [ROOT/"src"/"v062_growth_streams.py", ROOT/"src"/"v062_growth_engine.py",
              ROOT/"src"/"v062_benchmark_gate.py", ROOT/"scripts"/"v062_capture_growth_event.py",
              ROOT/"scripts"/"check_v062_growth_engine.py"]:
        check(f.exists(), f"{f.relative_to(ROOT)} exists")

    # 2. Stream registry
    print("2. Checking growth streams…")
    streams = list_streams()
    check(len(streams) == 12, f"12 growth streams ({len(streams)})")
    trainable = get_trainable_streams()
    check(len(trainable) > 0, f"{len(trainable)} trainable streams")
    approval = get_streams_requiring_approval()
    check(len(approval) > 0, f"{len(approval)} streams requiring approval")

    # 3. Capture events
    print("3. Testing growth event capture…")
    e1 = capture_growth_event("v059 passed and live routes select v055", stream_name="project_reports")
    check(e1.get("event_id") and e1.get("stream_name"), "project report captured")
    check(e1.get("trainable") is not None, "trainable flag set")

    e2 = capture_growth_event("The correct answer to who created you is Mr. Novotron", stream_name="dictionary_facts")
    check(e2.get("stream_name") == "dictionary_facts", "dictionary fact captured")

    e3 = capture_growth_event("Maybe this checkpoint is better", stream_name="conversation_corrections")
    check(e3.get("risk_level") is not None, "risk level set")

    # 4. Counts
    print("4. Checking stream counts…")
    counts = get_all_counts()
    check(len(counts) > 0, f"{len(counts)} streams have data")

    # ── verdict ────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"RESULTS: {len(PASSES)} passed, {len(ERRORS)} errors")
    for p in PASSES:
        print(p)
    for e in ERRORS:
        print(e)

    if ERRORS:
        print("\nFAIL: v062 check did not pass")
        return 1
    print("\nPASS: v062 growth engine installed and operating")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
