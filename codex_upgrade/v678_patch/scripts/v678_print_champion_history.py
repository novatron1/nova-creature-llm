#!/usr/bin/env python3
"""Gold print — v678 Champion History Tracker"""
import sys
from pathlib import Path
import json
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v678_champion_history import track_champion_history

def main():
    r = track_champion_history()
    version_str = r.get("version", "done")
    print(version_str)
    print(f"\nv678 — Champion History Tracker")
    for k, val in r.items():
        print(f"  {k}: {val}")
    report_dir = ROOT.parent / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "v678_gold.json"
    report_path.write_text(json.dumps(r if isinstance(r, dict) else {}, indent=2))
    print(f"\nGold report saved to {report_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
