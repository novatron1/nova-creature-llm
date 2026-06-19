#!/usr/bin/env python3
"""Gold print — v679 Checkpoint Battle Summary"""
import sys
from pathlib import Path
import json
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v679_battle_summary import generate_checkpoint_battle_summary

def main():
    r = generate_checkpoint_battle_summary()
    version_str = r.get("version", "done")
    print(version_str)
    print(f"\nv679 — Checkpoint Battle Summary")
    for k, val in r.items():
        print(f"  {k}: {val}")
    report_dir = ROOT.parent / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "v679_gold.json"
    report_path.write_text(json.dumps(r if isinstance(r, dict) else {}, indent=2))
    print(f"\nGold report saved to {report_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
