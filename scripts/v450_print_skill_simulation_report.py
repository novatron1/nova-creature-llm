#!/usr/bin/env python3
"""Print skill simulation report for v450."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v450_skill_simulation_report import generate_skill_simulation_report
import json
def main():
    r = generate_skill_simulation_report()
    print(json.dumps(r, indent=2))
    (ROOT/"reports"/"v450_real_world_skill_simulation_report.json").write_text(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
