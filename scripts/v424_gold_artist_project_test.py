#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v424_artist_project import simulate_artist_project
import json
def main():
    r = simulate_artist_project()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v424_gold_artist_project_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
