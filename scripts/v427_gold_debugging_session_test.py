#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v427_debugging_session import simulate_debugging_session
import json
def main():
    r = simulate_debugging_session()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v427_gold_debugging_session_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
