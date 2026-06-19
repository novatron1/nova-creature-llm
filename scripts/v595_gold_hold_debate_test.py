#!/usr/bin/env python3
"""Gold test for v595_debate_council."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v595_debate_council import hold_debate
import json
def main():
    r = hold_debate()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v595_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
