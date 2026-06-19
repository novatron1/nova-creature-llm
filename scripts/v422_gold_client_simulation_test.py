#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v422_client_conversation import simulate_client_conversation
import json
def main():
    r = simulate_client_conversation()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v422_gold_client_simulation_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
