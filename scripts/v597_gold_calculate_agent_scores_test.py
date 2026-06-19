#!/usr/bin/env python3
"""Gold test for v597_agent_scoreboard."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v597_agent_scoreboard import calculate_agent_scores
import json
def main():
    r = calculate_agent_scores()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v597_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
