#!/usr/bin/env python3
"""Check v076 auto patch repair."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v076_auto_patch_repair import create_broken_script, detect_error, repair_script, run_script
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  \u2705 {msg}")
    else: E.append(f"  \u274c {msg}")
def main():
    print("Nova v076 -- Auto Patch Repair Checker\n")
    c(Path(ROOT/"src"/"v076_auto_patch_repair.py").exists(), "src exists")
    path = create_broken_script()
    c(path is not None, "broken script created")
    err = detect_error(path)
    c(err["has_error"], "error detected")
    c(err.get("error_type") in ("SyntaxError", "NameError", "Unknown"), f"error type: {err.get('error_type')}")
    result = repair_script(path)
    c(result["success"], "repair succeeded")
    retest = run_script(path)
    c(retest["success"], "retest passes after repair")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
