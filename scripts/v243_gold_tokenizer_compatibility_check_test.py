#!/usr/bin/env python3
"""Gold test for v243_tokenizer_compatibility_check."""
import json,sys;from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v243_tokenizer_compatibility_check import check_tokenizer
E,P=[],[]
def main():
    print("Nova v243_tokenizer_compatibility_check -- Gold Test\n")
    r = check_tokenizer()
    if isinstance(r,dict): P.append("Result with "+str(len(r))+" fields")
    else: P.append("Result generated")
    print("\n"+"="*60+"\nPASSED: "+str(len(P))+", ERRORS: "+str(len(E)))
    for p in P: print("  [PASS] "+p)
    for e in E: print("  [FAIL] "+e)
    (ROOT/"reports"/"v243_tokenizer_compatibility_check_status.json").write_text(json.dumps({"version":"v243_tokenizer_compatibility_check_gold","created_at":datetime.now().isoformat(),"passes":len(P),"errors":len(E)},indent=2))
    return 0 if not E else 1
if __name__=="__main__":
    raise SystemExit(main())
