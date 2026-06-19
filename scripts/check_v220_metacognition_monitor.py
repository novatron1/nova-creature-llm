#!/usr/bin/env python3
"""Check v220_metacognition_monitor."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v220_metacognition_monitor import monitor_metacognition
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v220_metacognition_monitor -- Checker\n")
    c(Path(ROOT/"src"/"v220_metacognition_monitor.py").exists(), "src exists")
    r = monitor_metacognition()
    c(r is not None,"result generated")
    c(r["self_monitoring"],"self monitoring active")
    c(r["flags_contradictions"],"flags contradictions")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
