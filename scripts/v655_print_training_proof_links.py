#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from v655_weakness_to_training_proof_linker import link_weakness_to_training_proof
import json
def main(): r=link_weakness_to_training_proof(); print(json.dumps(r,indent=2)[:200]); (ROOT/"reports"/"v655_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
