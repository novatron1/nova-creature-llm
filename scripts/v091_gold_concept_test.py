#!/usr/bin/env python3
"""v091 — Gold concept test."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v091_concept_builder import build_concept
E, P = [], []
def main():
    print("Nova v091 -- Gold Concept Test\n")
    c = build_concept("benchmark advancement",
        ["improves score", "preserves old tests", "passes benchmark gate", "produces report"],
        ["adds files but no test", "adds dream layer but no quality check", "claims ability without self-map proof"])
    if len(c["examples"]) >= 3: P.append(f">=3 examples ({len(c['examples'])})")
    else: E.append(f"<3 examples ({len(c['examples'])})")
    if len(c["counterexamples"]) >= 2: P.append(f">=2 counterexamples ({len(c['counterexamples'])})")
    else: E.append(f"<2 counterexamples")
    if "benchmark" in c["pattern"].lower(): P.append("Benchmark in pattern")
    else: E.append("Benchmark not in pattern")
    if "benchmark" in c["rule"].lower(): P.append("Benchmark in rule")
    else: E.append("Benchmark not in rule")
    if c["training_candidate"] or c["approval_required"]: P.append("Training readiness defined")
    else: E.append("Training readiness missing")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(f"  [PASS] {p}")
    for e in E: print(f"  [FAIL] {e}")
    (ROOT/"reports"/"v091_gold_concept_test.json").write_text(json.dumps({"version":"v091_gold","passes":len(P),"errors":len(E)},indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
