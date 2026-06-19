#!/usr/bin/env python3
"""Check v464_patch_application_brain."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v464_patch_application_brain import apply_patch
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v464_patch_application_brain -- Checker\n")
    c(Path(ROOT/"src"/"v464_patch_application_brain.py").exists(), "src exists")
    r = apply_patch()
    c(r is not None, "result generated")
    c(isinstance(r, dict), "result is dict")
    c("version" in r, "version field present")
    c("module" in r, "module field present")
    c("created_at" in r, "created_at field present")
    c(r.get("real_hardware_enabled") == False, "real_hardware_enabled False")
    c(r.get("real_robot_movement_allowed") == False, "real_robot_movement_allowed False")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
