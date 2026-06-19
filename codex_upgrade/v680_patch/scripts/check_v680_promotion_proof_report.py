#!/usr/bin/env python3
"""Check v680 — Checkpoint Promotion Proof Report"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v680_promotion_proof_report import generate_checkpoint_promotion_proof_report

E, P = [], []

def c(cond, msg):
    if cond:
        P.append(f"  [PASS] {msg}")
    else:
        E.append(f"  [FAIL] {msg}")

def main():
    print(f"Nova v680_promotion_proof_report -- Checker\n")
    c(Path(ROOT / "src" / "v680_promotion_proof_report.py").exists(), "src exists")
    r = generate_checkpoint_promotion_proof_report()
    c(r is not None, "result generated")
    c(isinstance(r, dict), "result is dict")
    c(r.get("version") == "v680_promotion_proof_report", f"version field correct: {r.get('version')}")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P:
        print(p)
    for e in E:
        print(e)
    return 0 if not E else 1

if __name__ == "__main__":
    raise SystemExit(main())
