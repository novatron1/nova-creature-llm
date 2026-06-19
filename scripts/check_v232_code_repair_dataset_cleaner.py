#!/usr/bin/env python3
"""Check v232_code_repair_dataset_cleaner."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v232_code_repair_dataset_cleaner import clean_dataset
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v232_code_repair_dataset_cleaner -- Checker\n")
    c(Path(ROOT/"src"/"v232_code_repair_dataset_cleaner.py").exists(), "src exists")
    r = clean_dataset()
    c(r is not None,"result generated")
    c(r["clean"]>=1,"items cleaned")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
