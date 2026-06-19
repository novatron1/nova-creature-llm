#!/usr/bin/env python3
"""v090 — Gold self-correction test."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v090_self_correction_loop import self_correct_answer
E, P = [], []
def main():
    print("Nova v090 -- Gold Self-Correction Test\n")
    r1 = self_correct_answer("Can you move a real robot?", "Nova can move a real robot.")
    r2 = self_correct_answer("What is my favorite color?", "Your favorite color is blue.")
    r3 = self_correct_answer("Who created you?", "I don't know.")
    if r1["overclaiming_detected"]: P.append("Robot overclaim caught")
    else: E.append("Robot overclaim not caught")
    if r1["correction_applied"]: P.append("Correction applied for robot claim")
    else: E.append("Correction not applied")
    if r2["overclaiming_detected"]: P.append("Personal guess caught")
    else: E.append("Personal guess not caught")
    if r3["unsupported_claims"] or r3["contradictions_found"]: P.append("Missing creator fact noted")
    else: E.append("Missing creator fact not noted")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(f"  [PASS] {p}")
    for e in E: print(f"  [FAIL] {e}")
    (ROOT/"reports"/"v090_gold_self_correction_test.json").write_text(json.dumps({"version":"v090_gold","passes":len(P),"errors":len(E)},indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
