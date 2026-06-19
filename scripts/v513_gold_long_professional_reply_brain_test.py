#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v513_long_professional_reply_brain import draft_long_professional_reply
import json
def main():
    r = draft_long_professional_reply()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v513_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
