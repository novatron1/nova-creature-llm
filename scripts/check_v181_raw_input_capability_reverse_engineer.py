#!/usr/bin/env python3
"""Check v181_raw_input_capability_reverse_engineer."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v181_raw_input_capability_reverse_engineer import reverse_engineer_capabilities_from_input, get_pattern_types
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v181_raw_input_capability_reverse_engineer -- Checker\n")
    c(Path(ROOT/"src"/"v181_raw_input_capability_reverse_engineer.py").exists(), "src exists")
    items = [{"source":"math_qa","text":"12*12=144"},{"source":"identity_qa","text":"Who made you?"}]
    r = reverse_engineer_capabilities_from_input(items)
    c(r is not None, "result generated")
    c(r["input_count"] == 2, "inputs processed")
    c(len(r["inferred_capabilities"]) >= 1, "capabilities inferred")
    c(r["proof_required"], "proof required")
    pts = get_pattern_types()
    c(len(pts) >= 5, "pattern types defined")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
