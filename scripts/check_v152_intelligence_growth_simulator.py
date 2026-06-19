#!/usr/bin/env python3
"""Check v152_intelligence_growth_simulator."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v152_intelligence_growth_simulator import simulate_growth_mix, get_all_scenarios
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v152_intelligence_growth_simulator -- Checker\n")
    c(Path(ROOT/"src"/"v152_intelligence_growth_simulator.py").exists(), "src exists")
    r = simulate_growth_mix("fastest_safe_mix")
    c(r is not None, "result generated")
    c(r["reasoning_score"] >= 80, "fastest mix scores high")
    c(r["regression_risk"] <= 10, "low regression risk")
    s = get_all_scenarios()
    c(len(s) >= 5, "multiple scenarios modelled")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
