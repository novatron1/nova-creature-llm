#!/usr/bin/env python3
"""Gold print — v671 Candidate Checkpoint Registry"""
import sys
from pathlib import Path
import json
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v671_candidate_registry import register_candidate_checkpoint

def main():
    r = register_candidate_checkpoint()
    version_str = r.get("version", "done")
    print(version_str)
    print(f"\nv671 — Candidate Checkpoint Registry")
    for k, val in r.items():
        print(f"  {k}: {val}")
    report_dir = ROOT.parent / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "v671_gold.json"
    report_path.write_text(json.dumps(r if isinstance(r, dict) else {}, indent=2))
    print(f"\nGold report saved to {report_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
