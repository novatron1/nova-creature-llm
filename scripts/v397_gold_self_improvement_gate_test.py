#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v397_self_improvement_critic_gate import gate_self_improvement
import json
def main():
    r = gate_self_improvement()
    print(r.get("version","done"))
    (ROOT/"reports"/"v397_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__":
    raise SystemExit(main())
