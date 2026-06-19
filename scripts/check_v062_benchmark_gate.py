from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v062_benchmark_gate import run_benchmarks, check_gate, BENCHMARK_SUITE
from v062_multi_source_growth import analyze_training_sources

ERRORS = []
PASSES = []

def check(cond, msg):
    if cond:
        PASSES.append(f"  ✅ {msg}")
    else:
        ERRORS.append(f"  ❌ {msg}")

def main():
    print("Nova Creature v062 — Benchmark Gate + Multi-Source Checker\n")

    # 1. Files exist
    print("1. Checking v062 source files…")
    for f in [
        ROOT/"src"/"v062_benchmark_gate.py",
        ROOT/"src"/"v062_multi_source_growth.py",
        ROOT/"scripts"/"check_v062_benchmark_gate.py",
    ]:
        check(f.exists(), f"{f.relative_to(ROOT)} exists")

    # 2. Run benchmark suite
    print("2. Running benchmark suite ({0} tests)…".format(len(BENCHMARK_SUITE)))
    result = run_benchmarks()
    check(result["total"] == len(BENCHMARK_SUITE), f"All {len(BENCHMARK_SUITE)} tests executed")
    check(result["gate_passed"], f"Gate passed ({result['passed']}/{result['total']})")
    for r in result["results"]:
        check(r["passed"], f"{r['id']} passed")
        if not r["passed"]:
            ERRORS[-1] = ERRORS[-1].replace("✅", "❌")  # fix the emoji

    # 3. Check gate logic
    print("3. Checking gate logic…")
    gate = check_gate(result)
    check(gate["gate_passed"], "gate decision is passed")
    check(gate["action"] == "promote", f"action is promote (not {gate.get('action')})")

    # 4. Multi-source analysis
    print("4. Running multi-source analysis…")
    src_report = analyze_training_sources()
    check(src_report["total_lessons"] > 0, f"Total lessons: {src_report['total_lessons']}")
    check(src_report["source_count"] >= 1, f"Sources found: {src_report['source_count']}")

    # ── verdict ────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"RESULTS: {len(PASSES)} passed, {len(ERRORS)} errors")
    print(f"{'='*60}")
    for p in PASSES:
        print(p)
    for e in ERRORS:
        print(e)

    if ERRORS:
        print("\nFAIL: v062 check did not pass")
        return 1
    print("\nPASS: v062 benchmark gate active — no promotion without passing")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
