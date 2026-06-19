#!/usr/bin/env python3
"""Check v082 roadmap planner."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v082_long_term_roadmap_planner import build_roadmap
E,P=[], []
def c(cond, msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v082 -- Roadmap Checker\n")
    c((ROOT/"src"/"v082_long_term_roadmap_planner.py").exists(), "src exists")
    r = build_roadmap()
    c(len(r["completed_versions"]) >= 20, f"completed: {len(r['completed_versions'])}")
    c(len(r["active_versions"]) >= 15, f"active: {len(r['active_versions'])}")
    c("blocked_upgrades" in r, "blocked upgrades listed")
    c("robot_prerequisites" in r, "robot prerequisites")
    c("benchmark_required_for_future_steps" in r, "benchmark requirements")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p_ in P: print(p_)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
