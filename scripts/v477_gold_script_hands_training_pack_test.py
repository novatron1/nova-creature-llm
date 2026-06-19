#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v477_script_hands_training_pack import training_pack
import json
def main():
    r = training_pack()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v477_script_hands_training_pack_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
