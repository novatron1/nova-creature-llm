#!/usr/bin/env python3
"""Check v154_curriculum_engine."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v154_curriculum_engine import build_curriculum, get_queue
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v154_curriculum_engine -- Checker\n")
    c(Path(ROOT/"src"/"v154_curriculum_engine.py").exists(), "src exists")
    r = build_curriculum()
    c(r is not None, "result generated")
    c(r["count"] >= 8, f"{r["count"]} curriculum items")
    q = get_queue()
    c(len(q) >= 8, "queue available")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
