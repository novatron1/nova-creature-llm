#!/usr/bin/env python3
"""Check v227_data_to_skill_heatmap."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v227_data_to_skill_heatmap import build_heatmap
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v227_data_to_skill_heatmap -- Checker\n")
    c(Path(ROOT/"src"/"v227_data_to_skill_heatmap.py").exists(), "src exists")
    r = build_heatmap()
    c(r is not None,"result generated")
    c("strongest_stream" in r,"heatmap built")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
