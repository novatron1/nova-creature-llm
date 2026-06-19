#!/usr/bin/env python3
"""Gold test for v571_what_should_i_do_next_brain."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v571_what_should_i_do_next_brain import suggest_next_action
import json
def main():
    r = suggest_next_action()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v571_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
