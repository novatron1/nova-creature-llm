#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v496_research_bias_detector import detect_research_bias
import json
def main():
    r = detect_research_bias()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v496_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
