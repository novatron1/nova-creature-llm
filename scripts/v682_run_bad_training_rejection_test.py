#!/usr/bin/env python3
"""Test — v682 Bad Training Rejection Meter"""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v682_test_bad_training_rejection import test_bad_training_rejection
def main():
    r = test_bad_training_rejection()
    print(f"v682 — Bad Training Rejection Test")
    passed = 0; failed = 0
    for k, val in r.items():
        status = "PASS" if val in ("rejected","blocked","pending") else "INFO"
        if k == "none_approved":
            status = "PASS" if val else "FAIL"
        if status == "PASS":
            passed += 1
        else:
            failed += 1
        print(f"  [{status}] {k}: {val}")
    print(f"\nResult: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1
if __name__=="__main__": raise SystemExit(main())
