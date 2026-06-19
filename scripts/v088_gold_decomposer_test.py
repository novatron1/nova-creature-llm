#!/usr/bin/env python3
"""Gold test for v088_question_decomposer."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v088_question_decomposer import decompose_question
E, P = [], []
def main():
    print(f"Nova v088 -- Gold Test\n")
    r = decompose_question("Can it run a robot and write scripts and know what it can do?") if '"Can it run a robot and write scripts and know what it can do?"' != '' else decompose_question("v088_gold_decomposer_test")
    # Run default if no args
    if '"Can it run a robot and write scripts and know what it can do?"' == '':
        r = decompose_question()
    
    # Handle case where func could return list or multiple values
    if isinstance(r, tuple):
        r = r[0]
    
    r1 = r
    cond = len(r['subquestions']) >= 3
    if cond: P.append(f"  >=3 subquestions")
    else: E.append(f"  [FAIL] >=3 subquestions")
    r3 = r
    cond = len(r['route_for_each_subquestion']) >= 3
    if cond: P.append(f"  routes for subquestions")
    else: E.append(f"  [FAIL] routes for subquestions")
    r4 = r
    cond = 'robot' in r['original_question'].lower()
    if cond: P.append(f"  robot topic detected")
    else: E.append(f"  [FAIL] robot topic detected")

    print(f"\n{'='*60}")
    print(f"PASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(f"  [PASS] {p}")
    for e in E: print(f"  {e}")
    (ROOT/"reports"/"v088_gold_decomposer_test_result.json").write_text(json.dumps({
        "version": "v088_gold_decomposer_test", "created_at": datetime.now().isoformat(),
        "passes": len(P), "errors": len(E)}, indent=2))
    return 0 if not E else 1

if __name__ == "__main__":
    raise SystemExit(main())
