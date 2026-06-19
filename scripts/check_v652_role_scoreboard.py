#!/usr/bin/env python3
"""Check v652_role_brain_scoreboard."""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v652_role_brain_scoreboard import calculate_role_brain_scoreboard
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v652_role_brain_scoreboard -- Checker\n")
    c(Path(ROOT/"src"/"v652_role_brain_scoreboard.py").exists(),"src exists")
    r=calculate_role_brain_scoreboard(); c(r is not None,"result generated")
    roles=r.get("scores",{}); c(len(roles)==7,"7 roles tracked")
    c("planner_transformer" in roles,"planner_transformer present")
    c("memory_keeper" in roles,"memory_keeper present")
    c("critic_judge" in roles,"critic_judge present")
    c("robot_safety_monitor" in roles,"robot_safety_monitor present")
    c("project_continuity" in roles,"project_continuity present")
    c("speech_clarity" in roles,"speech_clarity present")
    c("capability_honesty" in roles,"capability_honesty present")
    c("score_categories" in r,"score categories defined")
    cats=r.get("score_categories",[]); c(len(cats)==5,"5 score categories")
    c("installation" in cats,"installation category present")
    c("intelligence_gain" in cats,"intelligence_gain category present")
    c("robustness" in cats,"robustness category present")
    c("promotion" in cats,"promotion category present")
    c("overall" in cats,"overall category present")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
