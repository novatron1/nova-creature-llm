#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v696_owner_review_promotion_packet import build_owner_review_promotion_packet
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v696_owner_review_promotion_packet -- Checker\n")
    c(Path(ROOT/"src"/"v696_owner_review_promotion_packet.py").exists(),"src exists")
    r=build_owner_review_promotion_packet(); c(r is not None,"result generated")
    pkt=r.get("packet",{}); c("candidate_summary" in pkt,"candidate summary present")
    c("benchmark_results" in pkt,"benchmark results present")
    c("owner_approval_line" in pkt,"owner approval line present")
    c("rollback_plan" in pkt,"rollback plan present")
    c(pkt.get("recommendation")=="promote","recommendation is promote")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
