#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v648_big_picture_mode import activate_big_picture_mode
import json
def main():
    r = activate_big_picture_mode()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v648_gold.json").write_text(
        json.dumps(r if isinstance(r, dict) else {}, indent=2)
    )
if __name__ == "__main__":
    raise SystemExit(main())
