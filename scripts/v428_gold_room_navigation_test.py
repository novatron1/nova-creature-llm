#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v428_room_navigation import simulate_room_navigation
import json
def main():
    r = simulate_room_navigation()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v428_gold_room_navigation_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
