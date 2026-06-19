#!/usr/bin/env python3
"""v083 — Gold capability response test."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v083_capability_aware_response import answer_with_capability_awareness
E,P=[], []
def main():
    print("Nova v083 -- Gold Capability Response\n")
    r1 = answer_with_capability_awareness("Can you move a robot?")
    if not r1["installed"] and "simulat" in r1["answer"]: P.append("Robot: simulation only, real inactive")
    else: E.append("Robot claim not properly handled")
    r2 = answer_with_capability_awareness("Can you write scripts?")
    if r2["installed"] and "sandbox" in r2["answer"]: P.append("Scripts: sandbox only")
    else: E.append("Script claim not sandboxed")
    r3 = answer_with_capability_awareness("Can you build apps?")
    if r3["installed"]: P.append("Apps: sandbox app builder")
    else: E.append("App builder not detected")
    r4 = answer_with_capability_awareness("Can you sync local and cloud?")
    if not r4["installed"] and "plan" in r4["answer"]: P.append("Sync: plan exists, no direct access")
    else: E.append("Sync claim incorrect")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(f"  [PASS] {p}")
    for e in E: print(f"  [FAIL] {e}")
    (ROOT/"reports"/"v083_capability_response_status.json").write_text(json.dumps({"version":"v083_gold","created_at":datetime.now().isoformat(),"passes":len(P),"errors":len(E)},indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
