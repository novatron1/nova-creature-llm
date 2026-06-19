#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v636_negotiation_simulator import simulate_negotiation
import json
def main():
    r = simulate_negotiation()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v636_gold.json").write_text(
        json.dumps(r if isinstance(r, dict) else {}, indent=2)
    )
if __name__ == "__main__":
    raise SystemExit(main())
