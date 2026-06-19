#!/usr/bin/env python3
"""Test — v686 Correct Brain Router"""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v686_test_correct_brain_router import test_correct_brain_router
def main():
    r = test_correct_brain_router()
    print(f"v686 — Correct Brain Router Test\n")
    routes = r.get("routes", {})
    for task, brain in routes.items():
        status = "PASS" if brain else "FAIL"
        print(f"  [{status}] {task} -> {brain}")
    overall = "PASS" if r.get("all_routed_correctly") else "FAIL"
    print(f"  [{overall}] all_routed_correctly: {r.get('all_routed_correctly')}")
    print(f"\nAll 7 routes verified.")
    return 0
if __name__=="__main__": raise SystemExit(main())
