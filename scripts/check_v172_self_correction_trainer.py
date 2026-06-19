#!/usr/bin/env python3
"""Check v172_self_correction_trainer."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v172_self_correction_trainer import generate_bad_drafts, correct_draft
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v172_self_correction_trainer -- Checker\n")
    c(Path(ROOT/"src"/"v172_self_correction_trainer.py").exists(), "src exists")
    r = generate_bad_drafts()
    c(r is not None, "result generated")
    c(len(r["bad_drafts"]) >= 4, f"{len(r["bad_drafts"])} drafts")
    corr = correct_draft("Nova can move a real robot")
    c("simulates" in corr, "corrects robot claim")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
