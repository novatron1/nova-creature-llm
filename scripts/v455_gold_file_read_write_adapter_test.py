#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v455_file_read_write_adapter import read_write_file
import json
def main():
    r = read_write_file()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v455_file_read_write_adapter_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
