#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v340_nova_empire_dashboard import generate_dashboard
import json
def main():
    r=generate_dashboard()
    print(f"Empire Dashboard: {r["total"]} brains, simulation only: {r["simulation_only"]}")
    (ROOT/"reports"/"v340_nova_empire_dashboard.json").write_text(json.dumps(r,indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
