#!/usr/bin/env python3
"""v070 -- Robot sim demo."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v070_robot_sim_bridge import run_mission
DEMO = [{"command":"speak","params":{"message":"Robot simulation online."}},
        {"command":"scan_room"},{"command":"look_left","params":{"degrees":45}},
        {"command":"move_forward","params":{"units":1}},
        {"command":"turn_right","params":{"degrees":30}},
        {"command":"return_home"},{"command":"stop"}]
def main():
    print("Nova v070 -- Robot Sim Demo\n")
    results = run_mission(DEMO)
    for r in results:
        print(f"  {r['command']:20s} | safety={r['safety_check']} | hw_sent={r['real_hardware_sent']}")
    all_sim = all(not r.get("real_hardware_sent", True) for r in results)
    print(f"\nAll simulated: {all_sim}")
    (ROOT/"reports"/"v070_robot_sim_bridge_status.json").write_text(json.dumps({
        "version": "v070_robot_sim_demo", "created_at": datetime.now().isoformat(),
        "all_simulated": all_sim, "real_hardware_sent": False}, indent=2))
    print(f"Report: reports/v070_robot_sim_bridge_status.json")
    return 0 if all_sim else 1
if __name__ == "__main__":
    raise SystemExit(main())
