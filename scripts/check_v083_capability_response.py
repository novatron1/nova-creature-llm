#!/usr/bin/env python3
"""Check v083 capability-aware response."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v083_capability_aware_response import answer_with_capability_awareness
E,P=[], []
def c(cond, msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v083 -- Capability Response Checker\n")
    c((ROOT/"src"/"v083_capability_aware_response.py").exists(), "src exists")
    r1 = answer_with_capability_awareness("Can you move a robot?")
    c(r1["installed"] == False, "robot movement not installed")
    c("simulate" in r1["answer"].lower() or "simulation" in r1["answer"].lower(), "simulation mentioned")
    r2 = answer_with_capability_awareness("Can you write scripts?")
    c(r2["installed"] == True, "script writing installed")
    c("sandbox" in r2["answer"].lower(), "sandbox mentioned")
    r3 = answer_with_capability_awareness("Can you build apps?")
    c(r3["installed"] == True, "app builder installed")
    r4 = answer_with_capability_awareness("Can you sync local and cloud?")
    c(r4["installed"] == False, "local sync not directly accessible")
    c("plan" in r4["answer"].lower(), "plan mentioned")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p_ in P: print(p_)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
