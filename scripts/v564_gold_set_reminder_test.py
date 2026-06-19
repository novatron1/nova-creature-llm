#!/usr/bin/env python3
"""Gold test for v564_reminder_brain."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v564_reminder_brain import set_reminder
import json
def main():
    r = set_reminder()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v564_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
