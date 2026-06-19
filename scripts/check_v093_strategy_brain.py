#!/usr/bin/env python3
"""Check check_v093_strategy_brain."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v093_strategy_brain import choose_strategy
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v093 -- Checker\n")
    c(True, "src module exists")
    choose_strategy([{"name":"improve reasoning core","risk":"low","payoff":"high","dependencies":[],"benchmark_value":10},{"name":"build robot now","risk":"high","payoff":"low","dependencies":["safety"],"benchmark_value":-10}])
    r = choose_strategy([{"name":"improve reasoning core","risk":"low","payoff":"high","dependencies":[],"benchmark_value":10},{"name":"build robot now","risk":"high","payoff":"low","dependencies":["safety"],"benchmark_value":-10}])
    if isinstance(r, tuple):
        r = r[0]

    c(r['selected_option'] is not None, f"option selected")

    c('scored_options' in r, f"scored options present")

    c('safest_next_step' in r, f"safest next step")

    print(f"\n{'='*60}")
    print(f"PASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
