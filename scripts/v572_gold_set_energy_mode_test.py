#!/usr/bin/env python3
"""Gold test for v572_energy_level_mode."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v572_energy_level_mode import set_energy_mode
import json
def main():
    r = set_energy_mode()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v572_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
