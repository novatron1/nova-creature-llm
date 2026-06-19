#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v547_answer_customer_question import answer_customer_question
import json
def main(): r=answer_customer_question(); print(r.get("version","done")); (ROOT/"reports"/"v547_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__": raise SystemExit(main())
