from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v067_vision_stream import process_visual_input, get_vision_log, get_stream_summary

ERRORS = []
PASSES = []

def check(cond, msg):
    PASSES.append(f"  {'✅' if cond else '❌'} {msg}")
    if not cond:
        ERRORS.append(msg)

def main():
    print("Nova Creature v067 — Vision Stream Checker\n")

    for f in [ROOT/"src"/"v067_vision_stream.py"]:
        check(f.exists(), f"{f.relative_to(ROOT)} exists")

    # Test logging a vision event (with non-existent image)
    result = process_visual_input("/tmp/test_vision.png", description="Test vision input")
    check(result["event_id"].startswith("vis_"), "event_id generated")
    check(result["status"] == "logged_no_vision_model", "status correct for no vision model")

    # Log should work
    log = get_vision_log()
    check(len(log) >= 1, f"vision log has {len(log)} entries")

    # Summary
    summary = get_stream_summary()
    check(summary["vision_model_connected"] == False, "vision_model reports disconnected")
    check(summary["status"] == "interface_defined_awaiting_model", "status correct")

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
