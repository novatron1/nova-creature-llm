#!/usr/bin/env python3
"""Check v180_fast_age_training_orchestrator."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v180_fast_age_training_orchestrator import run_orchestrator_dry_run, DRY_RUN_MODE

E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")

def main():
    print("Nova v180_fast_age_training_orchestrator -- Checker\n")
    c(Path(ROOT / "src" / "v180_fast_age_training_orchestrator.py").exists(), "src exists")
    c(DRY_RUN_MODE is True, "dry-run mode is default")
    r = run_orchestrator_dry_run()
    c(r is not None, "dry-run returns result")
    c(r.get("dry_run") is True, "dry_run flag true")
    c(r.get("all_steps_complete") is True, "all steps complete")
    c(r.get("expected_maturity_gain") is not None, "maturity gain reported")
    c("real_finetune_without_approval" in r, "safe flag present")
    c(r.get("real_finetune_without_approval") is False, "no real fine-tune without approval")
    c(len(r.get("steps", [])) >= 10, "at least 10 orchestration steps")

    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1

if __name__ == "__main__":
    raise SystemExit(main())
