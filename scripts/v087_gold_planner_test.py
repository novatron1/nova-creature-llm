#!/usr/bin/env python3
"""v087 — Gold planner test."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v087_multistep_planner import plan_goal
E, P = [], []
def main():
    print("Nova v087 -- Gold Planner Test\n")
    p = plan_goal("Make Nova smarter by improving reasoning, self-checking, and benchmarks.")
    if p["goal_type"] == "self_improvement": P.append("Self-improvement type detected")
    else: E.append("Wrong goal type")
    if len(p["steps"]) >= 5: P.append(f">=5 steps ({len(p['steps'])})")
    else: E.append(f"<5 steps ({len(p['steps'])})")
    if "safety_rules" in p: P.append("Safety rules present")
    else: E.append("Safety rules missing")
    if p["benchmark_required"]: P.append("Benchmark required")
    else: E.append("Benchmark not required")
    if "next_action" in p: P.append("Next action defined")
    else: E.append("Next action missing")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p_ in P: print(f"  [PASS] {p_}")
    for e in E: print(f"  [FAIL] {e}")
    (ROOT/"reports"/"v087_gold_planner_test.json").write_text(json.dumps({"version":"v087_gold","passes":len(P),"errors":len(E)},indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
