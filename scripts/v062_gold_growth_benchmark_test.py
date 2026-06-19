#!/usr/bin/env python3
"""v062 — Gold benchmark gate + growth engine test."""

import json, sys
from pathlib import Path
from datetime import datetime
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v062_benchmark_gate import run_benchmarks, check_gate, save_report, BENCHMARK_SUITE
from v062_growth_engine import capture_growth_event, get_all_counts

ERRORS = []
PASSES = []

def main():
    print("Nova Creature v062 — Gold Growth & Benchmark Test\n")

    # Phase 1: Benchmark
    print("Phase 1: Running benchmark gate\n")
    result = run_benchmarks()
    gate = check_gate(result)
    save_report(result, gate)

    print(f"  Tests: {result['total']}, Passed: {result['passed']}, Failed: {result['failed']}")
    print(f"  Rate: {result['pass_rate_pct']}%")
    print(f"  Gate: {gate['summary']}\n")

    if result["gate_passed"]:
        PASSES.append("Benchmark gate passed all tests")
    else:
        ERRORS.append("Benchmark gate failed:")
        for r in result["results"]:
            if not r["passed"]:
                ERRORS.append(f"  Failed: {r['id']}")

    # Phase 2: Growth engine
    print("Phase 2: Testing growth engine\n")
    e = capture_growth_event("Gold test: learning loop closed", stream_name="project_reports")
    if e.get("event_id"):
        PASSES.append("Growth engine captures events")
    else:
        ERRORS.append("Growth engine did not capture event")

    counts = get_all_counts()
    if len(counts) > 0:
        PASSES.append(f"Growth streams have data ({len(counts)} streams)")
    else:
        ERRORS.append("No growth stream data found")

    # Phase 3: Block check
    print("Phase 3: Verifying gate blocks failures\n")
    fake_fail = {"total": 1, "passed": 0, "failed": 1, "pass_rate_pct": 0.0, "gate_passed": False, "results": []}
    blocked_gate = check_gate(fake_fail, label="block_test")
    if not blocked_gate["gate_passed"] and blocked_gate["action"] == "block":
        PASSES.append("Gate correctly blocks on failure")
    else:
        ERRORS.append("Gate did not block on failure")

    # Save report
    report = {
        "version": "v062_gold_growth_benchmark_test",
        "created_at": datetime.now().isoformat(),
        "benchmark": {k: v for k, v in result.items() if k != "results"},
        "gate": gate,
        "errors": len(ERRORS),
        "passes": len(PASSES),
    }
    (ROOT / "reports" / "v062_gold_growth_benchmark_test.json").write_text(json.dumps(report, indent=2))

    print(f"\n{'='*60}")
    print(f"RESULTS: {len(PASSES)} passed, {len(ERRORS)} errors")
    for p in PASSES:
        print(f"  ✅ {p}")
    for e in ERRORS:
        print(f"  ❌ {e}")
    return 0 if not ERRORS else 1

if __name__ == "__main__":
    raise SystemExit(main())
