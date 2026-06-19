#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v514_message_approval_gate import gate_message_approval
import json
def main():
    r = gate_message_approval()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v514_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
