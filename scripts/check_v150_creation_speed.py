#!/usr/bin/env python3
"""Check v150_creation_speed."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v150_creation_speed_engine import plan_creation, get_creation_stats
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v150_creation_speed -- Checker\n")
    c(Path(ROOT/"src"/"v150_creation_speed_engine.py").exists(), "src exists")
    r = plan_creation("test idea")
    c(r is not None, "result generated")
    c(len(r.get("pipeline",[])) >= 5, "pipeline defined")
    stats = get_creation_stats()
    c(stats["total_lanes"] >= 8, f"{stats["total_lanes"]} lanes")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
