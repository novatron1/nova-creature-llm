#!/usr/bin/env python3
"""Check v211_intelligence_pressure_cooker."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v211_intelligence_pressure_cooker import run_pressure_cooker
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v211_intelligence_pressure_cooker -- Checker\n")
    c(Path(ROOT/"src"/"v211_intelligence_pressure_cooker.py").exists(), "src exists")
    r = run_pressure_cooker()
    c(r is not None,"result generated")
    c(r["safe_mode"],"safe mode active")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
