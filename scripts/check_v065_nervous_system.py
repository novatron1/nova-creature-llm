from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v065_nervous_system import run_all_tests, SELF_TESTS

ERRORS = []
PASSES = []

def check(cond, msg):
    PASSES.append(f"  {'✅' if cond else '❌'} {msg}")
    if not cond:
        ERRORS.append(msg)

def main():
    print("Nova Creature v065 — Nervous System Checker\n")

    # 1. Files exist
    print("1. Checking v065 source files…")
    for f in [ROOT/"src"/"v065_nervous_system.py"]:
        check(f.exists(), f"{f.relative_to(ROOT)} exists")

    # 2. All self-tests defined
    print("2. Checking self-test definitions…")
    check(len(SELF_TESTS) >= 10, f"{len(SELF_TESTS)} self-tests defined")

    # 3. Run all tests
    print("3. Running self-tests…")
    report = run_all_tests()
    check(report["total_tests"] == len(SELF_TESTS), "all tests executed")
    check(report["health"] in ("healthy", "degraded"), "health status reported")
    for r in report["results"]:
        check(r["passed"], f"{r['id']} {r['name']} passed")

    # ── verdict ────────────────────────────────────────────────────────────
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
