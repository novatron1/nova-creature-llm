#!/usr/bin/env python3
"""Gold test for v566_health_routine_tracker."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v566_health_routine_tracker import track_health_routine
import json
def main():
    r = track_health_routine()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v566_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
