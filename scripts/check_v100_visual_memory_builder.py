#!/usr/bin/env python3
"""Check v100_visual_memory_builder."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v100_visual_memory_builder import build_visual_memory
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v100 -- Checker\n")
    c(Path(ROOT/"src"/"v100_visual_memory_builder.py").exists(), "src exists")
    r = build_visual_memory({"text_or_description": "v095 passed 13/13.", "pass_fail_status": "pass"})
    c(r is not None, "result generated")
    if isinstance(r, dict): c(len(r) > 0, f"result fields: {len(r)}")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
