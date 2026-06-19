#!/usr/bin/env python3
"""Check v179_intelligence_gain_report."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v179_intelligence_gain_report import generate_gain_report, calculate_gain
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v179_intelligence_gain_report -- Checker\n")
    c(Path(ROOT/"src"/"v179_intelligence_gain_report.py").exists(), "src exists")
    r = generate_gain_report()
    c(r is not None, "result generated")
    c(r["overall_gain"] == "positive", "gain is positive")
    g = calculate_gain(80,95)
    c(g["gain"] == 15, "gain calculated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
