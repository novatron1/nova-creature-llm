#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v395_weakness_experiment_logger import log_weakness_experiment
import json
def main():
    r = log_weakness_experiment()
    print(r.get("version","done"))
    (ROOT/"reports"/"v395_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__":
    raise SystemExit(main())
