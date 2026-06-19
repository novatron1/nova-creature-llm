#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v476_computer_skill_benchmark import benchmark_skill
import json
def main():
    r = benchmark_skill()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v476_computer_skill_benchmark_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
