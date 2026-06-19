#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v615_manual_override_gate import gate_manual_override
import json
def main():
    r = gate_manual_override()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v615_gold.json").write_text(
        json.dumps(r if isinstance(r, dict) else {}, indent=2)
    )
if __name__ == "__main__":
    raise SystemExit(main())
