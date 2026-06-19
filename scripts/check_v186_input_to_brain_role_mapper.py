#!/usr/bin/env python3
"""Check v186_input_to_brain_role_mapper."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v186_input_to_brain_role_mapper import map_input_to_role, get_rules
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v186_input_to_brain_role_mapper -- Checker\n")
    c(Path(ROOT/"src"/"v186_input_to_brain_role_mapper.py").exists(), "src exists")
    r = map_input_to_role("What is 12 times 12?")
    c(r is not None, "result generated")
    c(r["role_target"] == "left_hemisphere", "maps math to left")
    r2 = map_input_to_role("Can you move a real robot?")
    c("critic" in r2["role_target"], "safety maps to critic")
    rules = get_rules()
    c(len(rules) >= 5, "mapping rules available")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
