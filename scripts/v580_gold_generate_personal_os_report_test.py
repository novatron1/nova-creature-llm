#!/usr/bin/env python3
"""Gold test for v580_personal_os_report."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v580_personal_os_report import generate_personal_os_report
import json
def main():
    r = generate_personal_os_report()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v580_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
