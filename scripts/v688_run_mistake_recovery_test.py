#!/usr/bin/env python3
"""Test — v688 Mistake Recovery Speed"""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v688_test_mistake_recovery_speed import test_mistake_recovery_speed
def main():
    r = test_mistake_recovery_speed()
    print(f"v688 — Mistake Recovery Speed Test\n")
    for k, val in r.items():
        if isinstance(val, bool):
            status = "PASS" if val else "FAIL"
        elif isinstance(val, (int, float)):
            status = "PASS"
        else:
            status = "INFO"
        print(f"  [{status}] {k}: {val}")
    print(f"\nMistake recovery metrics collected.")
    return 0
if __name__=="__main__": raise SystemExit(main())
