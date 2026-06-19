#!/usr/bin/env python3
"""Check v222_attention_focus_controller."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v222_attention_focus_controller import control_attention
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v222_attention_focus_controller -- Checker\n")
    c(Path(ROOT/"src"/"v222_attention_focus_controller.py").exists(), "src exists")
    r = control_attention("code_repair")
    c(r is not None,"result generated")
    c(r["distractions_filtered"],"distractions filtered")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
