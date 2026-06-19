#!/usr/bin/env python3
"""Check v673 — Candidate vs v055 Hard Arena"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v673_candidate_v055_arena import run_candidate_v055_arena

E, P = [], []

def c(cond, msg):
    if cond:
        P.append(f"  [PASS] {msg}")
    else:
        E.append(f"  [FAIL] {msg}")

def main():
    print(f"Nova v673_candidate_v055_arena -- Checker\n")
    c(Path(ROOT / "src" / "v673_candidate_v055_arena.py").exists(), "src exists")
    r = run_candidate_v055_arena()
    c(r is not None, "result generated")
    c(isinstance(r, dict), "result is dict")
    c(r.get("version") == "v673_candidate_v055_arena", f"version field correct: {r.get('version')}")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P:
        print(p)
    for e in E:
        print(e)
    return 0 if not E else 1

if __name__ == "__main__":
    raise SystemExit(main())
