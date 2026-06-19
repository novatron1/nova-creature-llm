from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v069_error_bank import log_error, get_errors, get_error_summary, mark_resolved

ERRORS = []
PASSES = []

def check(cond, msg):
    PASSES.append(f"  {'✅' if cond else '❌'} {msg}")
    if not cond:
        ERRORS.append(msg)

def main():
    print("Nova Creature v069 — Error Bank Checker\n")

    for f in [ROOT/"src"/"v069_error_bank.py"]:
        check(f.exists(), f"{f.relative_to(ROOT)} exists")

    # Log errors
    e1 = log_error("test", "python test.py", "Test error 1", category="test", severity="warning")
    check(e1["event_id"].startswith("err_"), "error event_id generated")
    check(not e1["resolved"], "new error starts unresolved")

    e2 = log_error("benchmark", "run.sh", "Benchmark failed", category="benchmark", severity="critical")
    check(e2["severity"] == "critical", "critical severity works")

    # Get errors
    errors = get_errors()
    check(len(errors) >= 2, f"get_errors returns {len(errors)} errors")

    # Unresolved filter
    unresolved = get_errors(unresolved_only=True)
    check(all(not e["resolved"] for e in unresolved), "unresolved filter works")

    # Mark resolved
    ok = mark_resolved(e1["event_id"])
    check(ok, "mark_resolved returns True")

    # Summary
    s = get_error_summary()
    check(s["total_errors"] >= 2, f"summary: {s['total_errors']} errors")
    check(s["unresolved"] >= 1, f"summary: {s['unresolved']} unresolved")
    check("category_counts" in s, "category_counts present")

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
