#!/usr/bin/env python3
"""Gold test for v575_life_admin_checklist."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v575_life_admin_checklist import generate_life_admin_checklist
import json
def main():
    r = generate_life_admin_checklist()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v575_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
