#!/usr/bin/env python3
"""Check v184_input_pattern_miner."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v184_input_pattern_miner import mine_input_patterns
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v184_input_pattern_miner -- Checker\n")
    c(Path(ROOT/"src"/"v184_input_pattern_miner.py").exists(), "src exists")
    r = mine_input_patterns(["data/capability_reverse_engineering"])
    c(r is not None, "result generated")
    c(r["no_files_modified"], "no files modified")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
