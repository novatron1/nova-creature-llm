#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v616_device_log_memory import log_device_action
import json
def main():
    r = log_device_action()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v616_gold.json").write_text(
        json.dumps(r if isinstance(r, dict) else {}, indent=2)
    )
if __name__ == "__main__":
    raise SystemExit(main())
