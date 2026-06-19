#!/usr/bin/env python3
"""Check v514_message_approval_gate."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v514_message_approval_gate import gate_message_approval
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v514_message_approval_gate -- Checker\n")
    c(Path(ROOT/"src"/"v514_message_approval_gate.py").exists(), "src exists")
    r = gate_message_approval()
    c(r is not None, "result generated")
    c(isinstance(r, dict), "result is dict")
    c("version" in r, "version field present")
    c("created_at" in r, "created_at field present")
    c("sim_only" in r, "sim_only field present")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
