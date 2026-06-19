#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v624_counterfactual_simulator import simulate_counterfactual
import json
def main():
    r = simulate_counterfactual()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v624_gold.json").write_text(
        json.dumps(r if isinstance(r, dict) else {}, indent=2)
    )
if __name__ == "__main__":
    raise SystemExit(main())
