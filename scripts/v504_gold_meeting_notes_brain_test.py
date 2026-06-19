#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v504_meeting_notes_brain import take_meeting_notes
import json
def main():
    r = take_meeting_notes()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v504_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
