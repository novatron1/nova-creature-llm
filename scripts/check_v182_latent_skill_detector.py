#!/usr/bin/env python3
"""Check v182_latent_skill_detector."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v182_latent_skill_detector import detect_latent_skills, get_skill_list
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v182_latent_skill_detector -- Checker\n")
    c(Path(ROOT/"src"/"v182_latent_skill_detector.py").exists(), "src exists")
    r = detect_latent_skills()
    c(r is not None, "result generated")
    c(r["total_detected"] >= 10, f"{r["total_detected"]} skills detected")
    sl = get_skill_list()
    c(len(sl) >= 10, "skill list available")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
