#!/usr/bin/env python3
"""Check v240_code_repair_growth_report."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v240_code_repair_growth_report import generate_report
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v240_code_repair_growth_report -- Checker\n")
    c(Path(ROOT/"src"/"v240_code_repair_growth_report.py").exists(), "src exists")
    r = generate_report()
    c(r is not None,"result generated")
    c(not r["promoted"],"not promoted")
    c("memory_recall" in r["next_weakest"],"next identified")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
