#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v426_game_design import simulate_game_design
import json
def main():
    r = simulate_game_design()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v426_gold_game_design_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
