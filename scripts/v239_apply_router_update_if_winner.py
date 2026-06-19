#!/usr/bin/env python3
"""Aux script."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v239_live_router_planner_update import check_router_update
def main():
    r=check_router_update(False); print(f'Update: {r["update_applied"]}, v055: {r["v055_preserved"]}')
    import json
    (ROOT/"reports"/"v239_apply_router_update_if_winner_status.json").write_text(json.dumps(r if isinstance(r,dict) else {"status":"done"},indent=2))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
