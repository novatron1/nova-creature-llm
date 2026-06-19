#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v451_computer_control_permission_map import get_permission_map
import json
def main():
    r = get_permission_map()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v451_computer_control_permission_map_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
