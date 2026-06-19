#!/usr/bin/env python3
"""Check v228_fast_age_cycle_dashboard."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v228_fast_age_cycle_dashboard import build_dashboard
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v228_fast_age_cycle_dashboard -- Checker\n")
    c(Path(ROOT/"src"/"v228_fast_age_cycle_dashboard.py").exists(), "src exists")
    r = build_dashboard()
    c(r is not None,"result generated")
    c(r["dashboard_ready"],"dashboard ready")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
