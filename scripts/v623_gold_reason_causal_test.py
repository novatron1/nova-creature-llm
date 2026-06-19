#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v623_causal_reasoning_brain import reason_causal
import json
def main():
    r = reason_causal()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v623_gold.json").write_text(
        json.dumps(r if isinstance(r, dict) else {}, indent=2)
    )
if __name__ == "__main__":
    raise SystemExit(main())
