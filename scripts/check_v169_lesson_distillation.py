#!/usr/bin/env python3
"""Check v169_lesson_distillation."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v169_lesson_distillation import distill_lesson
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v169_lesson_distillation -- Checker\n")
    c(Path(ROOT/"src"/"v169_lesson_distillation.py").exists(), "src exists")
    r = distill_lesson("Long Codex report about v095 passing all benchmarks.")
    c(r is not None, "result generated")
    c("core_lesson" in r, "lesson extracted")
    c(r["approval_required"], "approval required")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
