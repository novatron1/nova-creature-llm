#!/usr/bin/env python3
"""Check v208_capability_graduation_pipeline."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v208_capability_graduation_pipeline import run_graduation
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v208_capability_graduation_pipeline -- Checker\n")
    c(Path(ROOT/"src"/"v208_capability_graduation_pipeline.py").exists(), "src exists")
    r = run_graduation()
    c(r is not None,"result generated")
    c(r["total_stages"]==8,"8 stages")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
