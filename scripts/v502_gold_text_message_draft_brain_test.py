#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v502_text_message_draft_brain import draft_text_message
import json
def main():
    r = draft_text_message()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v502_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
