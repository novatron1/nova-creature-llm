#!/usr/bin/env python3
"""Print sync plan summary."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v079_local_cloud_sync_plan import build_sync_plan

def main():
    print("Nova v079 -- Sync Plan\n")
    p = build_sync_plan()
    print(f"Cloud stack: {len(p['cloud_version_stack'])} versions")
    print(f"  Latest: v{max(int(v[1:]) for v in p['cloud_version_stack'])}")
    print(f"Local access: {p['local_laptop_access']}")
    print(f"\nBrain checkpoints:")
    for ck in p["brain_slot_checkpoints"]:
        print(f"  {ck}")
    print(f"\nNever sync:")
    for ns in p["never_sync"]:
        print(f"  {ns}")
    print(f"\nApproval required:")
    for ar in p["approval_required_before_sync"]:
        print(f"  {ar}")
    print(f"\nReports to copy:")
    for rp in p["reports_that_need_copying"]:
        print(f"  {rp}")
    print(f"\nStatus: {p['status']}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
