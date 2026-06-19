from __future__ import annotations

import json, sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v062_benchmark_gate import run_benchmarks, check_gate, save_report, BENCHMARK_SUITE
from v062_multi_source_growth import analyze_training_sources, can_promote

ERRORS = []
PASSES = []

def main():
    print("Nova Creature v062 — Gold Gate Test\n")

    # Phase 1: Run benchmarks
    print("Phase 1: Benchmark execution\n")
    result = run_benchmarks()
    gate = check_gate(result)
    save_report(result, gate)

    print(f"  Tests: {result['total']}")
    print(f"  Passed: {result['passed']}")
    print(f"  Failed: {result['failed']}")
    print(f"  Rate: {result['pass_rate_pct']}%")
    print(f"  Gate: {gate['summary']}")
    print()

    if result["gate_passed"]:
        PASSES.append("Benchmark gate passed all tests")
    else:
        ERRORS.append("Benchmark gate failed")
        for r in result["results"]:
            if not r["passed"]:
                ERRORS.append(f"  Failed test: {r['id']}")

    # Phase 2: Multi-source analysis
    print("Phase 2: Multi-source growth analysis\n")
    src_report = analyze_training_sources()
    for src, count in sorted(src_report["source_breakdown"].items()):
        print(f"  {src}: {count} lessons")

    if src_report["source_count"] >= 1:
        PASSES.append(f"Multi-source analysis found {src_report['source_count']} sources")
    else:
        ERRORS.append("No training sources found")

    # Phase 3: Promote check
    print("\nPhase 3: Promotion eligibility\n")
    for src in src_report["source_breakdown"]:
        decision = can_promote(src, benchmark_passed=True)
        print(f"  {src}: promotable={decision['promotable']} — {decision['reason']}")
        if decision["promotable"]:
            PASSES.append(f"{src} is promotable when gate passes")
        else:
            ERROR.append(f"{src} is not promotable")

    # Phase 4: Block check — gate must block when tests fail
    print("\nPhase 4: Gate block verification\n")
    # Simulate a failing test by checking that if we had zero passes, gate would block
    fake_fail = {"total": 1, "passed": 0, "failed": 1, "pass_rate_pct": 0.0, "gate_passed": False, "results": []}
    blocked_gate = check_gate(fake_fail, label="block_test")
    if not blocked_gate["gate_passed"] and blocked_gate["action"] == "block":
        PASSES.append("Gate correctly blocks when benchmarks fail")
    else:
        ERRORS.append("Gate did not block on failure")

    print(f"  Block test: {blocked_gate['summary']}")

    # ── Final ──────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"RESULTS: {len(PASSES)} passed, {len(ERRORS)} errors")
    print(f"{'='*60}")
    for p in PASSES:
        print(f"  ✅ {p}")
    for e in ERRORS:
        print(f"  ❌ {e}")

    report = {
        "version": "v062_gold_gate_test",
        "created_at": datetime.now().isoformat(),
        "benchmark": {k: v for k, v in result.items() if k != "results"},
        "gate": gate,
        "multi_source": {k: v for k, v in src_report.items() if k != "roles"},
    }
    (ROOT / "reports" / "v062_gold_gate_test.json").write_text(json.dumps(report, indent=2))

    return 0 if not ERRORS else 1

if __name__ == "__main__":
    raise SystemExit(main())
