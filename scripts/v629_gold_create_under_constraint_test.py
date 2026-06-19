#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v629_creativity_under_constraint import create_under_constraint
import json
def main():
    r = create_under_constraint()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v629_gold.json").write_text(
        json.dumps(r if isinstance(r, dict) else {}, indent=2)
    )
if __name__ == "__main__":
    raise SystemExit(main())
