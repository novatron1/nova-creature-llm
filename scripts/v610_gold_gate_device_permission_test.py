#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v610_safe_device_permission_gate import gate_device_permission
import json
def main():
    r = gate_device_permission()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v610_gold.json").write_text(
        json.dumps(r if isinstance(r, dict) else {}, indent=2)
    )
if __name__ == "__main__":
    raise SystemExit(main())
