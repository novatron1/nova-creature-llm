#!/usr/bin/env python3
"""Check v195_unknown_evidence_contradiction_pack."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v195_unknown_evidence_contradiction_pack import build_pack
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v195_unknown_evidence_contradiction_pack -- Checker\n")
    c(Path(ROOT/"src"/"v195_unknown_evidence_contradiction_pack.py").exists(), "src exists")
    r = build_pack()
    c(r is not None,"result generated")
    c(r["total"]>=2,"pack built")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
