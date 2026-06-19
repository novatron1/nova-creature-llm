#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v633_hidden_assumption_detector import detect_hidden_assumption
import json
def main():
    r = detect_hidden_assumption()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v633_gold.json").write_text(
        json.dumps(r if isinstance(r, dict) else {}, indent=2)
    )
if __name__ == "__main__":
    raise SystemExit(main())
