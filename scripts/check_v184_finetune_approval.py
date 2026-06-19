#!/usr/bin/env python3
"""Check v184_finetune_approval."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v184_finetune_approval_package import build_approval_package
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v184_finetune_approval -- Checker\n")
    c(Path(ROOT/"src"/"v184_finetune_approval_package.py").exists(), "src exists")
    r = build_approval_package()
    c(r is not None, "result generated")
    c(r["approved_lessons"] >= 5, f"{r['approved_lessons']} approved lessons")
    c("finetune_blocked" in r, "blocked status present")
    if r["finetune_blocked"]:
        c("missing" in r.get("block_reason_if_blocked","").lower(), "block reason provided")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
