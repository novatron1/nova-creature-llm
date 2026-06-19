#!/usr/bin/env python3
"""Check v168_concept_compression."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v168_concept_compression import compress_concept, get_examples
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v168_concept_compression -- Checker\n")
    c(Path(ROOT/"src"/"v168_concept_compression.py").exists(), "src exists")
    r = compress_concept("Benchmark advancement means no upgrade promotes unless it improves or preserves test scores.")
    c(r is not None, "result generated")
    c("compressed" in r, "compressed output")
    ex = get_examples()
    c(len(ex) >= 1, "examples available")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
