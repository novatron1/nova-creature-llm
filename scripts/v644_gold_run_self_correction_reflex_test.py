#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v644_self_correction_reflex import run_self_correction_reflex
import json
def main():
    r = run_self_correction_reflex()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v644_gold.json").write_text(
        json.dumps(r if isinstance(r, dict) else {}, indent=2)
    )
if __name__ == "__main__":
    raise SystemExit(main())
