#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v360_multi_robot_architecture_report import generate_architecture_report
import json
def main():
    r = generate_architecture_report()
    print(f"Architecture Report: {r['total_modules']} modules, status: {r['architecture_status']}")
    (ROOT/"reports"/"v360_multi_robot_architecture_report.json").write_text(json.dumps(r, indent=2))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
