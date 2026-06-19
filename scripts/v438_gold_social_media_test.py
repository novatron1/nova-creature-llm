#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v438_social_media_growth import simulate_social_media_growth
import json
def main():
    r = simulate_social_media_growth()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v438_gold_social_media_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
