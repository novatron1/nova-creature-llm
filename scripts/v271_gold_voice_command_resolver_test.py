#!/usr/bin/env python3
"""Gold test for v271_voice_command_resolver."""
import json,sys;from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v271_voice_command_resolver import resolve
E,P=[],[]
def main():
    print("Nova v271_voice_command_resolver -- Gold Test\n")
    r = resolve()
    if isinstance(r,dict): P.append("Result with "+str(len(r))+" fields")
    else: P.append("Result generated")
    print("\n"+"="*60+"\nPASSED: "+str(len(P))+", ERRORS: "+str(len(E)))
    for p in P: print("  [PASS] "+p)
    for e in E: print("  [FAIL] "+e)
    (ROOT/"reports"/"v271_voice_command_resolver_status.json").write_text(json.dumps({"version":"v271_voice_command_resolver_gold","created_at":datetime.now().isoformat(),"passes":len(P),"errors":len(E)},indent=2))
    return 0 if not E else 1
if __name__=="__main__":
    raise SystemExit(main())
