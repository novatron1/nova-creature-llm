#!/usr/bin/env python3
"""Gold test for v599_agent_benchmark."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v599_agent_benchmark import run_agent_benchmark
import json
def main():
    r = run_agent_benchmark()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v599_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
