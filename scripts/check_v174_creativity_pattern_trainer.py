#!/usr/bin/env python3
"""Check v174_creativity_pattern_trainer."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v174_creativity_pattern_trainer import generate_creative_patterns
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v174_creativity_pattern_trainer -- Checker\n")
    c(Path(ROOT/"src"/"v174_creativity_pattern_trainer.py").exists(), "src exists")
    r = generate_creative_patterns("app_ideas")
    c(r is not None, "result generated")
    c(r["stays_within_evidence"], "evidence-bound")
    c(len(r["patterns"]) >= 3, "patterns generated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
