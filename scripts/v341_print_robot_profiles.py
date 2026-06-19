#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v341_robot_profile_registry import create_robot_profile
import json
def main():
    r = create_robot_profile()
    print(f"Robot Profiles: {len(r)} fields")
    (ROOT/"reports"/"v341_robot_profile_registry_report.json").write_text(json.dumps(r, indent=2))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
