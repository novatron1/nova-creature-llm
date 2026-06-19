#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v433_video_treatment import simulate_video_treatment
import json
def main():
    r = simulate_video_treatment()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v433_gold_video_treatment_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
