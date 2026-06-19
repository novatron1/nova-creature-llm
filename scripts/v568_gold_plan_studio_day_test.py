#!/usr/bin/env python3
"""Gold test for v568_studio_day_planner."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v568_studio_day_planner import plan_studio_day
import json
def main():
    r = plan_studio_day()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v568_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
