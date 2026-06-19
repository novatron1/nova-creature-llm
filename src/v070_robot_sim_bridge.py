"""v070 — Robot Simulation Bridge. real_hardware_sent always false."""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = ROOT / "data" / "robot_sim" / "robot_command_history.jsonl"

def simulate_command(name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    from v070_robot_command_schema import validate_command
    v = validate_command(name, params)
    if not v["valid"]:
        return {"error": v["error"], "simulated": False}
    params = v["params"]
    schema = v["schema"]
    safety_check = not schema["safety_check_required"]
    sim_map = {
        "stop": "SIMULATED: stopped",
        "scan_room": "SIMULATED: room scan complete",
        "return_home": "SIMULATED: returned to home",
        "move_forward": f"SIMULATED: moved forward {params.get('units', 1)} units",
        "move_backward": f"SIMULATED: moved backward {params.get('units', 1)} units",
        "turn_left": f"SIMULATED: turned left {params.get('degrees', 90)} deg",
        "turn_right": f"SIMULATED: turned right {params.get('degrees', 90)} deg",
        "look_left": f"SIMULATED: looked left {params.get('degrees', 45)} deg",
        "look_right": f"SIMULATED: looked right {params.get('degrees', 45)} deg",
        "speak": f"SIMULATED: says '{params.get('message', '')}'",
    }
    sim_result = sim_map.get(name, f"SIMULATED: {name}")
    record = {"command": name, "parameters": params or {}, "reason": f"Simulated {name}",
              "safety_check": safety_check, "simulated_result": sim_result,
              "real_hardware_sent": False, "timestamp": datetime.now().isoformat()}
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record

def run_mission(commands: list[dict]) -> list[dict]:
    return [simulate_command(cmd.get("command", ""), cmd.get("params")) for cmd in commands]

def get_history(limit: int = 20) -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    lines = [l for l in HISTORY_PATH.read_text().splitlines() if l.strip()]
    history = []
    for line in lines[-limit:]:
        try:
            history.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return history

def main():
    print("Nova v070 -- Robot Sim Bridge\n")
    demo = [{"command": "speak", "params": {"message": "Robot simulation online"}},
            {"command": "scan_room"}, {"command": "look_left", "params": {"degrees": 45}},
            {"command": "move_forward", "params": {"units": 1}},
            {"command": "turn_right", "params": {"degrees": 30}},
            {"command": "return_home"}, {"command": "stop"}]
    results = run_mission(demo)
    for r in results:
        print(f"  {r['command']:20s} | safety={r['safety_check']} | hw_sent={r['real_hardware_sent']}")
    all_sim = all(not r.get("real_hardware_sent", True) for r in results)
    print(f"\nAll simulated: {all_sim}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
