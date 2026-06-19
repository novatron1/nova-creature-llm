#!/usr/bin/env python3
"""Check v084 owner approval console."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v084_owner_approval_console import submit_for_approval, approve_item, reject_item, list_pending, list_history, CATEGORIES
E,P=[], []
def c(cond, msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v084 -- Approval Console Checker\n")
    c((ROOT/"src"/"v084_owner_approval_console.py").exists(), "src exists")
    c(len(CATEGORIES) == 8, f"8 categories ({len(CATEGORIES)})")
    r = submit_for_approval("memory_training", "Approve training candidate")
    c(r["status"] == "pending", f"submitted: {r['id']}")
    r2 = approve_item(r["id"])
    c(r2["success"], "approved")
    c(r2["item"]["status"] == "approved", "status updated")
    r3 = reject_item("nonexistent")
    c(not r3["success"], "nonexistent reject fails gracefully")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p_ in P: print(p_)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
