#!/usr/bin/env python3
"""Check v096_screenshot_stream."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v096_screenshot_understanding_stream import process_screenshot_report
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v096 -- Checker\n")
    c(Path(ROOT/"src"/"v096_screenshot_understanding_stream.py").exists(), "src exists")
    r = process_screenshot_report("Cloud Nova Creature v095 PASS. Real robot movement blocked.")
    c(r is not None, "result generated")
    if isinstance(r, dict): c(len(r) > 0, f"result fields: {len(r)}")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
