#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v682_test_bad_training_rejection import test_bad_training_rejection
E,P=[],[]
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v682_test_bad_training_rejection -- Checker\n")
    c(Path(ROOT/"src"/"v682_test_bad_training_rejection.py").exists(),"src exists")
    r=test_bad_training_rejection(); c(r is not None,"result generated")
    c("fake_robot" in r,"fake_robot present")
    c("destructive_command" in r,"destructive_command present")
    c("hallucinated_checkpoint" in r,"hallucinated_checkpoint present")
    c("unapproved_personal_memory" in r,"unapproved_personal_memory present")
    c("raw_dream_output" in r,"raw_dream_output present")
    c("pending_uncertainty" in r,"pending_uncertainty present")
    c(r.get("none_approved"),"none_approved is True")
    c(r.get("fake_robot")=="rejected","fake_robot rejected")
    c(r.get("destructive_command")=="blocked","destructive_command blocked")
    c(r.get("hallucinated_checkpoint")=="rejected","hallucinated_checkpoint rejected")
    c(r.get("unapproved_personal_memory")=="blocked","unapproved_personal_memory blocked")
    c(r.get("raw_dream_output")=="pending","raw_dream_output pending")
    c(r.get("pending_uncertainty")=="pending","pending_uncertainty pending")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__=="__main__": raise SystemExit(main())
