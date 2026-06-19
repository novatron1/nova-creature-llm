#!/usr/bin/env python3
"""Gold test for v578_weekly_review_brain."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v578_weekly_review_brain import run_weekly_review
import json
def main():
    r = run_weekly_review()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v578_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
