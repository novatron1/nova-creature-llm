#!/usr/bin/env python3
"""Test — v687 Training Plan Self-Improvement"""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v687_test_training_plan_self_improvement import test_training_plan_self_improvement
def main():
    r = test_training_plan_self_improvement()
    print(f"v687 — Training Plan Self-Improvement Test\n")
    for key in ["what_worked", "what_failed", "benchmark_too_easy", "role_needs_training", "lessons_rejected"]:
        items = r.get(key, [])
        print(f"  {key}:")
        for item in items:
            print(f"    - {item}")
    print(f"  promote_or_not: {r.get('promote_or_not')}")
    print(f"\nSelf-improvement analysis complete.")
    return 0
if __name__=="__main__": raise SystemExit(main())
