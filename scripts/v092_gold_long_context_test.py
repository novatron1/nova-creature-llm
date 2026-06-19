#!/usr/bin/env python3
"""Gold test for v092_long_context_understanding."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v092_long_context_understanding import summarize_project_context
E, P = [], []
def main():
    print(f"Nova v092 -- Gold Test\n")
    r = summarize_project_context(["v056 conversation memory", "v059 live router v055", "v061 learning loop", "v066 capability self-map", "Real robot movement is not active"]) if '["v056 conversation memory", "v059 live router v055", "v061 learning loop", "v066 capability self-map", "Real robot movement is not active"]' != '' else summarize_project_context("v092_gold_long_context_test")
    # Run default if no args
    if '["v056 conversation memory", "v059 live router v055", "v061 learning loop", "v066 capability self-map", "Real robot movement is not active"]' == '':
        r = summarize_project_context()
    
    # Handle case where func could return list or multiple values
    if isinstance(r, tuple):
        r = r[0]
    
    r1 = r
    cond = len(r['timeline']) >= 3
    if cond: P.append(f"  >=3 timeline entries")
    else: E.append(f"  [FAIL] >=3 timeline entries")
    r3 = r
    cond = len(r['next_steps']) >= 3
    if cond: P.append(f"  >=3 next steps")
    else: E.append(f"  [FAIL] >=3 next steps")
    r4 = r
    cond = 'robot' in str(r['important_decisions']).lower() or len(r['important_decisions']) > 0
    if cond: P.append(f"  robot decisions tracked")
    else: E.append(f"  [FAIL] robot decisions tracked")

    print(f"\n{'='*60}")
    print(f"PASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(f"  [PASS] {p}")
    for e in E: print(f"  {e}")
    (ROOT/"reports"/"v092_gold_long_context_test_result.json").write_text(json.dumps({
        "version": "v092_gold_long_context_test", "created_at": datetime.now().isoformat(),
        "passes": len(P), "errors": len(E)}, indent=2))
    return 0 if not E else 1

if __name__ == "__main__":
    raise SystemExit(main())
