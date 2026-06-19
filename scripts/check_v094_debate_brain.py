#!/usr/bin/env python3
"""Check check_v094_debate_brain."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v094_debate_brain import run_debate
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v094 -- Checker\n")
    c(True, "src module exists")
    run_debate("Should Nova enable real robot movement now?")
    r = run_debate("Should Nova enable real robot movement now?")
    if isinstance(r, tuple):
        r = r[0]

    c(len(r['role_arguments']) >= 3, f">=3 roles")

    c('final_decision' in r, f"decision made")

    c('risks' in r, f"risks listed")

    print(f"\n{'='*60}")
    print(f"PASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
