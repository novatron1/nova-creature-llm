#!/usr/bin/env python3
"""Check v342_body_adapter_standard."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v342_body_adapter_standard import define_body_adapter_standard
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v342_body_adapter_standard -- Checker\n")
    c(Path(ROOT/"src"/"v342_body_adapter_standard.py").exists(), "src exists")
    r = define_body_adapter_standard()
    c(r is not None, "result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
