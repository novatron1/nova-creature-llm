#!/usr/bin/env python3
"""Check v070 robot sim bridge."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v070_robot_command_schema import list_commands, validate_command
from v070_robot_sim_bridge import simulate_command, run_mission
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  \u2705 {msg}")
    else: E.append(f"  \u274c {msg}")
def main():
    print("Nova v070 -- Robot Sim Checker\n")
    c(Path(ROOT/"src"/"v070_robot_command_schema.py").exists(), "schema exists")
    c(Path(ROOT/"src"/"v070_robot_sim_bridge.py").exists(), "bridge exists")
    cmds = list_commands()
    c(len(cmds) == 10, f"10 commands ({len(cmds)})")
    v = validate_command("stop")
    c(v["valid"], "stop valid")
    v2 = validate_command("nonexistent")
    c(not v2["valid"], "bad cmd invalid")
    r = simulate_command("stop")
    c(r.get("real_hardware_sent") == False, "stop hw=false")
    c("SIMULATED" in r.get("simulated_result",""), "stop simulated")
    r2 = simulate_command("move_forward", {"units": 2})
    c(r2.get("real_hardware_sent") == False, "move hw=false")
    c("2" in r2.get("simulated_result",""), "move units")
    mission = [{"command":"speak","params":{"message":"t"}},{"command":"scan_room"},{"command":"stop"}]
    results = run_mission(mission)
    c(len(results) == 3, "3 cmds ran")
    all_sim = all(not r.get("real_hardware_sent",True) for r in results)
    c(all_sim, "all simulated")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
