#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src"))
from v227_data_to_skill_heatmap import build_heatmap; import json
def main():
    r = build_heatmap(); print(f"Data-to-Skill Heatmap\n")
    for stream, skills in r["heatmap"].items():
        print(f"  {stream}: {', '.join(skills)}")
    print(f"\nStrongest stream: {r['strongest_stream']}")
    print(f"Highest transfer: {r['highest_skill_transfer']}")
    (ROOT/"reports"/"v227_data_heatmap.json").write_text(json.dumps(r,indent=2)); return 0
if __name__ == "__main__": raise SystemExit(main())
