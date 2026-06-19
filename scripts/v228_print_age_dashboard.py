#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src"))
from v228_fast_age_cycle_dashboard import build_dashboard; import json
def main():
    r = build_dashboard(); m = r["metrics"]
    print(f"Fast-Age Cycle Dashboard\n")
    for k,v in m.items(): print(f"  {k}: {v}")
    (ROOT/"reports"/"v228_age_dashboard.json").write_text(json.dumps(r,indent=2)); return 0
if __name__ == "__main__": raise SystemExit(main())
