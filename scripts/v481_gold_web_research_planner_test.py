#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v481_web_research_planner import plan_web_research
import json
def main():
    r = plan_web_research()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v481_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
