#!/usr/bin/env python3
"""Gold test for v570_project_dashboard."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v570_project_dashboard import generate_project_dashboard
import json
def main():
    r = generate_project_dashboard()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v570_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
