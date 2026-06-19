#!/usr/bin/env python3
"""Gold test for v577_goal_progress_tracker."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v577_goal_progress_tracker import track_goal_progress
import json
def main():
    r = track_goal_progress()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v577_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
