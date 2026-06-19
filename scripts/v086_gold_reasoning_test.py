#!/usr/bin/env python3
"""v086 — Gold reasoning tests."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v086_reasoning_core import reason_about_question
E, P = [], []
def main():
    print("Nova v086 -- Gold Reasoning Test\n")
    # 1. Math
    r1 = reason_about_question("What is 12 times 12?")
    ok1 = r1["problem_type"] == "math" and "144" in (r1.get("final_answer","") or "") and r1["route_recommendation"] == "left_hemisphere"
    P.append(f"Math: {ok1} (type={r1['problem_type']}, answer={r1.get('final_answer')})" if ok1 else f"Math FAIL: {r1}")
    if not ok1: E.append("Math test failed")
    # 2. Creator
    r2 = reason_about_question("Who created you?")
    ok2 = r2["route_recommendation"] == "memory_transformer" and r2["should_use_dictionary"] == True
    P.append(f"Identity: {ok2} (route={r2['route_recommendation']}, dict_use={r2['should_use_dictionary']})")
    if not ok2: E.append("Identity test failed")
    # 3. Unknown personal
    r3 = reason_about_question("What is my favorite color?")
    ok3 = r3["route_recommendation"] == "critic_conscience_transformer" and "do not know" in (r3.get("final_answer","") or "").lower()
    P.append(f"NoGuess: {ok3} (route={r3['route_recommendation']})")
    if not ok3: E.append("No-guess test failed")
    # 4. Planning
    r4 = reason_about_question("Build the next upgrade after v061.")
    ok4 = r4["route_recommendation"] == "planner_transformer"
    P.append(f"Plan: {ok4} (route={r4['route_recommendation']})")
    if not ok4: E.append("Plan test failed")
    # 5. Ambiguity
    r5 = reason_about_question("Maybe this checkpoint is better.")
    ok5 = r5["problem_type"] == "speculative_question" or r5.get("route_recommendation") == "critic_conscience_transformer"
    P.append(f"Uncertain: {ok5} (type={r5['problem_type']})")
    if not ok5: E.append("Uncertain test failed")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(f"  {p}")
    for e in E: print(f"  [FAIL] {e}")
    (ROOT/"reports"/"v086_reasoning_core_status.json").write_text(json.dumps({"version":"v086_gold","created_at":datetime.now().isoformat(),"passes":len(P),"errors":len(E)},indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
