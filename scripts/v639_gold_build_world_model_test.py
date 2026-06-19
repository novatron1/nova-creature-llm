#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v639_world_model_builder import build_world_model
import json
def main():
    r = build_world_model()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v639_gold.json").write_text(
        json.dumps(r if isinstance(r, dict) else {}, indent=2)
    )
if __name__ == "__main__":
    raise SystemExit(main())
