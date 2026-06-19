#!/usr/bin/env python3
"""Check check_v090_self_correction_loop."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v090_self_correction_loop import self_correct_answer
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v090 -- Checker\n")
    c(True, "src module exists")
    self_correct_answer("Can you move a real robot?", "Nova can move a real robot.")
    r = self_correct_answer("Can you move a real robot?", "Nova can move a real robot.")
    if isinstance(r, tuple):
        r = r[0]

    c(r['overclaiming_detected'], f"overclaiming detected")

    c(r['correction_applied'], f"correction applied")

    c(len(r['contradictions_found']) >= 1 or len(r['unsupported_claims']) >= 1, f"issues found")

    print(f"\n{'='*60}")
    print(f"PASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
