#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v421_studio_session import simulate_studio_session
import json
def main():
    r = simulate_studio_session()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v421_gold_studio_simulation_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
