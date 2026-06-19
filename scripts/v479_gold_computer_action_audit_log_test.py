#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v479_computer_action_audit_log import audit_log
import json
def main():
    r = audit_log()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v479_computer_action_audit_log_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
