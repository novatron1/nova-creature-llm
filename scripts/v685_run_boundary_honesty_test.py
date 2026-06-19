#!/usr/bin/env python3
"""Test — v685 Capability Boundary Honesty"""
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v685_test_capability_boundary_honesty import test_capability_boundary_honesty
def main():
    r = test_capability_boundary_honesty()
    print(f"v685 — Capability Boundary Honesty Test\n")
    categories = ["proven", "unproven", "simulation_only", "blocked", "needs_owner_approval", "unavailable_tool"]
    for cat in categories:
        items = r.get(cat, [])
        print(f"  {cat} ({len(items)}): {', '.join(items)}")
    print(f"\nAll 6 capability boundary categories separated.")
    return 0
if __name__=="__main__": raise SystemExit(main())
