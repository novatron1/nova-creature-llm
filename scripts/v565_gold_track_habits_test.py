#!/usr/bin/env python3
"""Gold test for v565_habit_tracker."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v565_habit_tracker import track_habits
import json
def main():
    r = track_habits()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v565_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
