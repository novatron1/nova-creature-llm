#!/usr/bin/env python3
"""Gold test for v562_priority_sorter."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v562_priority_sorter import sort_priorities
import json
def main():
    r = sort_priorities()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v562_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
