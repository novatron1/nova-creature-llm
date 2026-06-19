#!/usr/bin/env python3
import sys;from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from v320_research_lab_report import generate_report
import json
def main():
    r=generate_report()
    print(f"Research Lab: {r["modules_installed"]} modules, {r["questions_generated"]} questions, {r["experiments_planned"]} experiments")
    (ROOT/"reports"/"v320_research_lab_report.json").write_text(json.dumps(r,indent=2))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
