#!/usr/bin/env python3
"""Check v180_fast_age_training_orchestrator."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v180_fast_age_training_orchestrator import run_orchestrator_dry_run, simulate_full_cycle
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v180_fast_age_training_orchestrator -- Checker\n")
    c(Path(ROOT/"src"/"v180_fast_age_training_orchestrator.py").exists(), "src exists")
    r = run_orchestrator_dry_run()
    c(r is not None, "result generated")
    c(r["dry_run"], "dry-run mode")
    c(r["total_steps"] >= 8, f"{r["total_steps"]} steps")
    c(not r["real_finetune_without_approval"], "no auto finetune")
    s = simulate_full_cycle()
    c(s["cycle_complete"], "full cycle works")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
