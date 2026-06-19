#!/usr/bin/env python3
"""Check v079 local/cloud sync plan."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v079_local_cloud_sync_plan import build_sync_plan
E,P=[], []
def c(cond, msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v079 -- Cloud Sync Checker\n")
    c((ROOT/"src"/"v079_local_cloud_sync_plan.py").exists(), "src exists")
    p = build_sync_plan()
    c(len(p["cloud_version_stack"]) >= 20, f"cloud stack {len(p['cloud_version_stack'])} versions")
    c(len(p["never_sync"]) >= 5, f"never-sync patterns: {len(p['never_sync'])}")
    c("local_laptop_access" in p, "local access flag present")
    c(p["local_laptop_access"] == False, "no local access assumed")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p_ in P: print(p_)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
