#!/usr/bin/env python3
"""Check v127_voice_identity."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v127_voice_identity_mode import get_voice_identity
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v127_voice_identity -- Checker\n")
    c(Path(ROOT/"src"/"v127_voice_identity_mode.py").exists(), "src exists")
    r = get_voice_identity()
    c(r is not None, "result generated")
    c(r.get('does_not_fake_abilities'), "does not fake abilities")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
