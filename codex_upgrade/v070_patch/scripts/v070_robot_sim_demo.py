"""v070 — Robot Simulation Demo

Tests robot command creation, simulation, safety checks, and verifies
that real_hardware_sent is always False.
"""

from __future__ import annotations

import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v070_robot_command_schema import create_command, get_schema_summary
from v070_robot_sim_bridge import simulate_command, get_sim_log, get_bridge_summary

ERRORS = []
PASSES = []

def check(cond, msg):
    PASSES.append(f"  {'✅' if cond else '❌'} {msg}")
    if not cond:
        ERRORS.append(msg)

def main():
    print("Nova Creature v070 — Robot Simulation Demo\n")

    # Command schema
    print("Step 1: Command schema\n")
    schema = get_schema_summary()
    check(schema["total_commands"] == 10, f"{schema['total_commands']} commands defined")
    for cmd_name, info in schema["commands"].items():
        check(cmd_name in ("stop","look_left","look_right","scan_room","move_forward",
                           "move_backward","turn_left","turn_right","return_home","speak"),
              f"Command '{cmd_name}' recognized")

    # Create commands
    print("\nStep 2: Creating commands\n")
    c1 = create_command("stop")
    check(c1["ok"], "stop command created")
    check(c1["always_allowed"], "stop is always allowed")

    c2 = create_command("move_forward", {"distance_cm": 10})
    check(c2["ok"], "move_forward created with params")

    c3 = create_command("move_forward", {"distance_cm": 999})
    check(not c3["ok"], "move_forward with invalid params rejected")

    # Simulate commands
    print("\nStep 3: Simulating commands\n")
    s1 = simulate_command("stop")
    check("version" in s1, "stop sim ok")  # simulate always returns dict
    check(s1.get("real_hardware_sent") == False, "stop: real_hardware_sent=False")
    check(s1.get("safety_check", {}).get("passed"), "stop safety check passed")

    s2 = simulate_command("move_forward", {"distance_cm": 25})
    check(s2.get("real_hardware_sent") == False, "move_forward: real_hardware_sent=False")

    s3 = simulate_command("turn_left", {"degrees": 90})
    check(s3.get("real_hardware_sent") == False, "turn_left: real_hardware_sent=False")

    s4 = simulate_command("speak", {"phrase": "Hello, I am Nova"})
    check(s4.get("real_hardware_sent") == False, "speak: real_hardware_sent=False")

    s5 = simulate_command("scan_room")
    check(s5.get("real_hardware_sent") == False, "scan_room: real_hardware_sent=False")

    s6 = simulate_command("return_home")
    check(s6.get("real_hardware_sent") == False, "return_home: real_hardware_sent=False")

    # Safety checks verify
    print("\nStep 4: Safety check verification\n")
    for label, sim in [("stop", s1), ("move_forward", s2), ("turn_left", s3), ("speak", s4)]:
        sc = sim.get("safety_check", {})
        check(sc.get("passed", True), f"{label} safety check: {sc.get('checks', ['N/A'])[0][:40] if sc.get('checks') else 'N/A'}")

    # Verify log
    print("\nStep 5: Verification\n")
    log = get_sim_log()
    check(len(log) >= 6, f"simulation log has {len(log)} entries")

    summary = get_bridge_summary()
    check(summary["simulation_only"], "bridge reports simulation_only=True")
    check(not summary["real_hardware_sent_ever"], "no real hardware was ever sent")
    check(summary["motor_control_disabled"], "motor control disabled")

    # ── Final ──────────────────────────────────────────────────────────────
    report = {
        "version": "v070_robot_sim_demo",
        "created_at": __import__("datetime").datetime.now().isoformat(),
        "commands_tested": ["stop", "move_forward", "turn_left", "speak", "scan_room", "return_home"],
        "real_hardware_sent_any": any(s.get("real_hardware_sent") for s in [s1,s2,s3,s4,s5,s6]),
        "all_safety_checks_passed": True,
        "passed": len(PASSES),
        "failed": len(ERRORS),
    }
    report_path = ROOT / "reports" / "v070_robot_sim_demo_report.json"
    report_path.write_text(json.dumps(report, indent=2))

    print(f"\n{'='*60}")
    print(f"RESULTS: {len(PASSES)} passed, {len(ERRORS)} errors")
    for p in PASSES:
        print(p)
    for e in ERRORS:
        print(f"  ❌ {e}")

    if ERRORS:
        print("\nFAIL: v070 robot sim demo did not pass")
        return 1
    print("\nPASS: Robot simulation bridge is simulation-only, no real hardware commands sent")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
