#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v694_next_training_target_selector import select_next_training_target
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v694_next_training_target_selector -- Checker\n")
    c(Path(ROOT/"src"/"v694_next_training_target_selector.py").exists(),"src exists")
    r=select_next_training_target(); c(r is not None,"result generated")
    criteria=r.get("selection_criteria",{}); c(len(criteria)==6,"6 selection criteria")
    c(r.get("recommended_target") is not None,"recommended target present")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
