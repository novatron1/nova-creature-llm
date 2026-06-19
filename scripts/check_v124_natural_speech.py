#!/usr/bin/env python3
"""Check v124_natural_speech."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v124_natural_speech_layer import naturalize_response
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v124_natural_speech -- Checker\n")
    c(Path(ROOT/"src"/"v124_natural_speech_layer.py").exists(), "src exists")
    r = naturalize_response("test")
    c(r is not None, "result generated")
    c(r['accuracy_preserved'], "accuracy preserved")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
