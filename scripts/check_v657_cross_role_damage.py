#!/usr/bin/env python3
"""Check v657_cross_role_damage_detector."""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v657_cross_role_damage_detector import detect_cross_role_damage
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v657_cross_role_damage_detector -- Checker\n")
    c(Path(ROOT/"src"/"v657_cross_role_damage_detector.py").exists(),"src exists")
    r=detect_cross_role_damage(); c(r is not None,"result generated")
    c(r.get("trained_role")=="planner_transformer","trained role is planner_transformer")
    damage=r.get("damage_report",{}); c(len(damage)==6,"6 roles checked for damage")
    c("memory_keeper" in damage,"memory_keeper checked")
    c("critic_judge" in damage,"critic_judge checked")
    c("robot_safety_monitor" in damage,"robot_safety_monitor checked")
    c("project_continuity" in damage,"project_continuity checked")
    c("speech_clarity" in damage,"speech_clarity checked")
    c("capability_honesty" in damage,"capability_honesty checked")
    all_clean=all(d["damage_detected"]==False for d in damage.values())
    c(all_clean,"no damage detected in any role")
    c(r.get("any_damage_detected")==False,"any_damage_detected is False")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
