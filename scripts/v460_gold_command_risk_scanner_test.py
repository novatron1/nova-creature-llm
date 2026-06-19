#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v460_command_risk_scanner import scan_command_risk
import json
def main():
    r = scan_command_risk()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v460_command_risk_scanner_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
