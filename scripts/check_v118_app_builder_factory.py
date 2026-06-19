#!/usr/bin/env python3
"""Check v118_app_builder_factory."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v118_app_builder_factory import app_builder_factory
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v118_app_builder_factory -- Checker\n")
    c(Path(ROOT/"src"/"v118_app_builder_factory.py").exists(), "src exists")
    r = app_builder_factory("test")
    c(r is not None, "result generated")
    c(len(r.get('capabilities',[])) >= 3, "capabilities defined")
    c(r.get('sandbox_only'), "sandbox only")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
