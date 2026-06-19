#!/usr/bin/env python3
"""Check v182_targeted_role_exporter."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v182_targeted_role_training_exporter import export_targeted_training
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v182_targeted_role_exporter -- Checker\n")
    c(Path(ROOT/"src"/"v182_targeted_role_training_exporter.py").exists(), "src exists")
    r = export_targeted_training()
    c(r is not None, "result generated")
    c(len(r["role_counts"]) >= 5, f"{len(r['role_counts'])} roles exported")
    exp_dir = ROOT/"exports"/"v182_targeted_role_training_sets"
    c(exp_dir.exists(), "export directory exists")
    for role in ["planner_transformer","memory_transformer","critic_conscience_transformer"]:
        c((exp_dir/f"{role}.jsonl").exists(), f"{role}.jsonl exists")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
