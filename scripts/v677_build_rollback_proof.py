#!/usr/bin/env python3
"""Gold print — v677 Rollback Proof Builder"""
import sys
from pathlib import Path
import json
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v677_rollback_proof import build_rollback_proof

def main():
    r = build_rollback_proof()
    version_str = r.get("version", "done")
    print(version_str)
    print(f"\nv677 — Rollback Proof Builder")
    for k, val in r.items():
        print(f"  {k}: {val}")
    report_dir = ROOT.parent / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "v677_gold.json"
    report_path.write_text(json.dumps(r if isinstance(r, dict) else {}, indent=2))
    print(f"\nGold report saved to {report_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
