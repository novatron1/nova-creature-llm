#!/usr/bin/env python3
"""Print — v690 Learning Quality Proof Report"""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v690_generate_learning_quality_proof_report import generate_learning_quality_proof_report
import json
def main():
    r = generate_learning_quality_proof_report()
    print(f"v690 — Learning Quality Proof Report")
    for k, val in r.items():
        if isinstance(val, dict):
            print(f"  {k}:")
            for sk, sv in val.items():
                print(f"    {sk}: {sv}")
        else:
            print(f"  {k}: {val}")
    report_dir = ROOT / "reports"
    report_path = report_dir / "v681_to_v690_learning_quality_proof_status.json"
    print(f"\nConsolidated report saved to {report_path}")
    return 0
if __name__=="__main__": raise SystemExit(main())
