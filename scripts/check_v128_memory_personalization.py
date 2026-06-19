#!/usr/bin/env python3
"""Check v128_memory_personalization."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v128_memory_personalization import personalize_response
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v128_memory_personalization -- Checker\n")
    c(Path(ROOT/"src"/"v128_memory_personalization.py").exists(), "src exists")
    r = personalize_response("test")
    c(r is not None, "result generated")
    c(not r.get('uses_pending_memory'), "no pending memory")
    c(not r.get('uses_rejected_memory'), "no rejected memory")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
