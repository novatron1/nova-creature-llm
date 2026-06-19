#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v641_model_mistake_classifier import classify_model_mistake
E, P = [], []
def c(cond, msg):
    if cond:
        P.append(f"  [PASS] {msg}")
    else:
        E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v641_model_mistake_classifier -- Checker\n")
    c(Path(ROOT / "src" / "v641_model_mistake_classifier.py").exists(), "src exists")
    r = classify_model_mistake()
    c(r is not None, "result generated")
    if isinstance(r, dict):
        c("version" in r, "version field present")
        c("safe" in r, "safe field present")
        c("simulation" in r, "simulation field present")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P:
        print(p)
    for e in E:
        print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
