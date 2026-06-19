#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v457_app_control_adapter import control_app
import json
def main():
    r = control_app()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v457_app_control_adapter_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
