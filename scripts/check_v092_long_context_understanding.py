#!/usr/bin/env python3
"""Check check_v092_long_context_understanding."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v092_long_context_understanding import summarize_project_context
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v092 -- Checker\n")
    c(True, "src module exists")
    summarize_project_context(["v056", "v059", "v061", "v066"])
    r = summarize_project_context(["v056", "v059", "v061", "v066"])
    if isinstance(r, tuple):
        r = r[0]

    c(len(r['timeline']) >= 2, f"timeline entries")

    c(len(r['next_steps']) >= 3, f">=3 next steps")

    c('completed_versions' in r, f"completed versions")

    print(f"\n{'='*60}")
    print(f"PASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
