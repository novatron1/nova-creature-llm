#!/usr/bin/env python3
"""Check v099_file_folder_visual_inspector."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v099_file_folder_visual_inspector import inspect_file_folder_listing
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v099 -- Checker\n")
    c(Path(ROOT/"src"/"v099_file_folder_visual_inspector.py").exists(), "src exists")
    r = inspect_file_folder_listing("checkpoints/base/creature_v032_bigfit_twenty_plain.pt\nreports/v095_intelligence_benchmark_status.json")
    c(r is not None, "result generated")
    if isinstance(r, dict): c(len(r) > 0, f"result fields: {len(r)}")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
