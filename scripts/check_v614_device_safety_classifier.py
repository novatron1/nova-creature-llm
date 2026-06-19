#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v614_device_safety_classifier import classify_device_safety
E, P = [], []
def c(cond, msg):
    if cond:
        P.append(f"  [PASS] {msg}")
    else:
        E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v614_device_safety_classifier -- Checker\n")
    c(Path(ROOT / "src" / "v614_device_safety_classifier.py").exists(), "src exists")
    r = classify_device_safety()
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
