#!/usr/bin/env python3
"""Check v395_weakness_experiment_logger."""
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v395_weakness_experiment_logger import log_weakness_experiment
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v395_weakness_experiment_logger -- Checker\n")
    c(Path(ROOT/"src"/"v395_weakness_experiment_logger.py").exists(),"src exists")
    r = log_weakness_experiment()
    c(r is not None,"result generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__":
    raise SystemExit(main())
