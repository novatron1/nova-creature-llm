#!/usr/bin/env python3
"""Check v121_personality_style."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v121_personality_style_brain import apply_style
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v121_personality_style -- Checker\n")
    c(Path(ROOT/"src"/"v121_personality_style_brain.py").exists(), "src exists")
    r = apply_style("facts_only","test")
    c(r is not None, "result generated")
    c(r.get('preserves_facts'), "facts preserved")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
