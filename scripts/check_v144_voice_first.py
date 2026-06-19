#!/usr/bin/env python3
"""Check v144_voice_first."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v144_voice_first_intelligence import voice_answer
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v144_voice_first -- Checker\n")
    c(Path(ROOT/"src"/"v144_voice_first_intelligence.py").exists(), "src exists")
    r = voice_answer("test")
    c(r is not None, "result generated")
    c(r.get("no_fake_robot_movement"), "no fake robot")
    c(r.get("no_fake_tool_access"), "no fake tools")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
