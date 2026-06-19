#!/usr/bin/env python3
"""Check v676 — Router Promotion Dry-Run"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v676_router_promotion_dry_run import run_router_promotion_dry_run

E, P = [], []

def c(cond, msg):
    if cond:
        P.append(f"  [PASS] {msg}")
    else:
        E.append(f"  [FAIL] {msg}")

def main():
    print(f"Nova v676_router_promotion_dry_run -- Checker\n")
    c(Path(ROOT / "src" / "v676_router_promotion_dry_run.py").exists(), "src exists")
    r = run_router_promotion_dry_run()
    c(r is not None, "result generated")
    c(isinstance(r, dict), "result is dict")
    c(r.get("version") == "v676_router_promotion_dry_run", f"version field correct: {r.get('version')}")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P:
        print(p)
    for e in E:
        print(e)
    return 0 if not E else 1

if __name__ == "__main__":
    raise SystemExit(main())
