#!/usr/bin/env python3
"""Gold test for v093_strategy_brain."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v093_strategy_brain import choose_strategy
E, P = [], []
def main():
    print(f"Nova v093 -- Gold Test\n")
    r = choose_strategy([{"name":"build robot movement now","risk":"high","payoff":"low","dependencies":["safety","sensors","hardware"],"benchmark_value":-10},{"name":"improve reasoning core","risk":"low","payoff":"high","dependencies":[],"benchmark_value":10},{"name":"build benchmark dashboard","risk":"low","payoff":"medium","dependencies":[],"benchmark_value":7}]) if '[{"name":"build robot movement now","risk":"high","payoff":"low","dependencies":["safety","sensors","hardware"],"benchmark_value":-10},{"name":"improve reasoning core","risk":"low","payoff":"high","dependencies":[],"benchmark_value":10},{"name":"build benchmark dashboard","risk":"low","payoff":"medium","dependencies":[],"benchmark_value":7}]' != '' else choose_strategy("v093_gold_strategy_test")
    # Run default if no args
    if '[{"name":"build robot movement now","risk":"high","payoff":"low","dependencies":["safety","sensors","hardware"],"benchmark_value":-10},{"name":"improve reasoning core","risk":"low","payoff":"high","dependencies":[],"benchmark_value":10},{"name":"build benchmark dashboard","risk":"low","payoff":"medium","dependencies":[],"benchmark_value":7}]' == '':
        r = choose_strategy()
    
    # Handle case where func could return list or multiple values
    if isinstance(r, tuple):
        r = r[0]
    
    r1 = r
    cond = r['selected_option'] is not None
    if cond: P.append(f"  option selected")
    else: E.append(f"  [FAIL] option selected")
    r3 = r
    cond = 'robot' not in r['selected_option'].lower() or r['score'] < 0
    if cond: P.append(f"  robot not selected (blocked)")
    else: E.append(f"  [FAIL] robot not selected (blocked)")
    r4 = r
    cond = 'reasoning' in r['selected_option'].lower()
    if cond: P.append(f"  reasoning preferred")
    else: E.append(f"  [FAIL] reasoning preferred")

    print(f"\n{'='*60}")
    print(f"PASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(f"  [PASS] {p}")
    for e in E: print(f"  {e}")
    (ROOT/"reports"/"v093_gold_strategy_test_result.json").write_text(json.dumps({
        "version": "v093_gold_strategy_test", "created_at": datetime.now().isoformat(),
        "passes": len(P), "errors": len(E)}, indent=2))
    return 0 if not E else 1

if __name__ == "__main__":
    raise SystemExit(main())
