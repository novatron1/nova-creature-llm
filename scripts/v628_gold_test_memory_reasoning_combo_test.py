#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v628_memory__plus_reasoning_combo_test import test_memory_reasoning_combo
import json
def main():
    r = test_memory_reasoning_combo()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v628_gold.json").write_text(
        json.dumps(r if isinstance(r, dict) else {}, indent=2)
    )
if __name__ == "__main__":
    raise SystemExit(main())
