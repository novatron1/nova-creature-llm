#!/usr/bin/env python3
"""Check v450_skill_simulation_report."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v450_skill_simulation_report import generate_skill_simulation_report
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v450_skill_simulation_report -- Checker\n")
    c(Path(ROOT/"src"/"v450_skill_simulation_report.py").exists(), "src exists")
    r = generate_skill_simulation_report()
    c(r is not None, "result generated")
    c(isinstance(r, dict), "result is dict")
    c(r.get("simulation") == True, "simulation flag True")
    c(r.get("trainable") == False, "trainable flag False")
    c(r.get("real_hardware_enabled") == False, "real_hardware_enabled False")
    c(r.get("real_robot_movement_allowed") == False, "real_robot_movement_allowed False")
    c("version" in r, "version field present")
    c("module" in r, "module field present")
    c("created_at" in r, "created_at field present")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
