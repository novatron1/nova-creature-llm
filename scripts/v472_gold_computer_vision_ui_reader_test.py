#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v472_computer_vision_ui_reader import read_ui
import json
def main():
    r = read_ui()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v472_computer_vision_ui_reader_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
