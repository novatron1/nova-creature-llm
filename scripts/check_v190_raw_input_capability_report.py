#!/usr/bin/env python3
"""Check v190_raw_input_capability_report."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v190_raw_input_capability_report import generate_capability_report, get_report_summary
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v190_raw_input_capability_report -- Checker\n")
    c(Path(ROOT/"src"/"v190_raw_input_capability_report.py").exists(), "src exists")
    r = generate_capability_report()
    c(r is not None, "result generated")
    c(r["promote_ready"], "report ready")
    s = get_report_summary()
    c(s["proven"] >= 1, "proven capabilities tracked")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
