#!/usr/bin/env python3
"""Check v171_evidence_ranking_trainer."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v171_evidence_ranking_trainer import rank_evidence, get_priority
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v171_evidence_ranking_trainer -- Checker\n")
    c(Path(ROOT/"src"/"v171_evidence_ranking_trainer.py").exists(), "src exists")
    r = rank_evidence("benchmark_report")
    c(r is not None, "result generated")
    c(r["rank"] == 1, "benchmark is top priority")
    p = get_priority()
    c(len(p) >= 5, "priority list defined")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
