#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v393_experiment_runner_sim import run_sim_experiment
import json
def main():
    r = run_sim_experiment()
    print(r.get("version","done"))
    (ROOT/"reports"/"v393_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {},indent=2))
if __name__=="__main__":
    raise SystemExit(main())
