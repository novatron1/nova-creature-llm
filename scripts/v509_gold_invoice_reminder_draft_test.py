#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v509_invoice_reminder_draft_brain import draft_invoice_reminder
import json
def main():
    r = draft_invoice_reminder()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v509_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
