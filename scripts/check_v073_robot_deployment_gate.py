#!/usr/bin/env python3
"""Check v073 deployment gate."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v073_robot_deployment_gate import check_deployment_readiness, REQUIREMENTS
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  \u2705 {msg}")
    else: E.append(f"  \u274c {msg}")
def main():
    print("Nova v073 -- Deployment Gate Checker\n")
    c(Path(ROOT/"src"/"v073_robot_deployment_gate.py").exists(), "src exists")
    r = check_deployment_readiness()
    c(r["deployment_ready"] == False, "deployment blocked by default")
    c(r["real_robot_movement_allowed"] == False, "real movement blocked")
    c(r["all_requirements_met"] == False, "not all met (default)")
    c(len(r["missing_requirements"]) == 12, f"12 missing reqs ({len(r['missing_requirements'])})")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
