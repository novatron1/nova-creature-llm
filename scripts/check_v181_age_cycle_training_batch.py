#!/usr/bin/env python3
"""Check v181_age_cycle_training_batch."""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v181_age_cycle_training_batch_builder import build_training_batch
AGE_DIR = ROOT / "data" / "intelligence_age_cycle"
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v181_age_cycle_training_batch -- Checker\n")
    c(Path(ROOT/"src"/"v181_age_cycle_training_batch_builder.py").exists(), "src exists")
    r = build_training_batch()
    c(r is not None, "result generated")
    c(r["approved"] >= 5, f"{r['approved']} approved items")
    c(r["rejected"] >= 1, "rejected items exist")
    c("code_repair" in r["weaknesses_targeted"], "code repair targeted")
    c("unknown_handling" in r["weaknesses_targeted"], "unknown handling targeted")
    c(AGE_DIR.exists(), "data dir exists")
    for f in ["approved_training_batch.jsonl","rejected_training_batch.jsonl","pending_training_batch.jsonl"]:
        c((AGE_DIR/f).exists(), f"{f} created")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
