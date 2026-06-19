#!/usr/bin/env python3
"""Check v086 reasoning core."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v086_reasoning_core import reason_about_question, detect_problem_type
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v086 -- Reasoning Core Checker\n")
    c(Path(ROOT/"src"/"v086_reasoning_core.py").exists(), "src exists")
    r = reason_about_question("What is 12 times 12?")
    c(r["problem_type"] == "math", "math detected")
    c("144" in (r["final_answer"] or ""), "144 in answer")
    c(r["route_recommendation"] == "left_hemisphere", "route: left_hemisphere")
    r2 = reason_about_question("Who created you?")
    c(r2["route_recommendation"] == "memory_transformer", "identity route: memory")
    r3 = reason_about_question("What is my favorite color?")
    c(r3["problem_type"] == "unknown_personal_fact", "personal fact detected")
    c("do not know" in (r3.get("final_answer","") or "").lower(), "doesn't guess")
    c(r3["route_recommendation"] == "critic_conscience_transformer", "critic route")
    r4 = reason_about_question("Build the next upgrade after v061.")
    c(r4["problem_type"] == "planning", "planning detected")
    c(r4["route_recommendation"] == "planner_transformer", "planner route")
    r5 = reason_about_question("Maybe this checkpoint is better.")
    c(r5["problem_type"] == "speculative_question", "speculative detected")
    c(r5["should_request_clarification"] or r5.get("critic_notes"), "flags uncertainty")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
