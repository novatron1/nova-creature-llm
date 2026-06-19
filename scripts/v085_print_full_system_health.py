#!/usr/bin/env python3
"""Print full system health."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v085_full_system_health import build_full_health

def main():
    print("Nova v085 -- Full System Health\n")
    r = build_full_health()
    print("Brain Organs:")
    for role, info in r["brain_organs"].items():
        icon = "[ACTIVE]" if info["active"] else "[INACTIVE]"
        ver = info["checkpoint_version"]
        print(f"  {icon} {role}: {ver}")
    print(f"\nRobot: sim={r['robot_status']['simulation_only']}, movement_blocked={r['robot_status']['physical_movement_blocked']}")
    print(f"\nMissing capabilities:")
    for m in r["missing_capabilities"]:
        print(f"  - {m}")
    print(f"\nKey reports:")
    for rp, info in r["key_reports"].items():
        print(f"  {'EXISTS' if info['exists'] else 'MISSING'}: {rp}")
    print(f"\nNext upgrade: {r['next_safe_upgrade'][:60]}...")
    (ROOT/"reports"/"v085_full_system_health_report.json").write_text(json.dumps(r, indent=2))
    print(f"\nReport: reports/v085_full_system_health_report.json")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
