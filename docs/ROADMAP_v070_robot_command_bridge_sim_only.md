# v070 — Robot Command Bridge (Simulation-Only)

## Purpose
Nova can plan and simulate robot actions. No real motor control. All movement is simulation-only.

## Files to create later
- src/v070_robot_command_schema.py
- src/v070_robot_sim_bridge.py
- scripts/v070_robot_sim_demo.py

## Safety rules
- real_hardware_sent must always be false.
- No motor control, no GPIO, no serial motor commands.
- All movement commands must pass safety simulation.
- Stop command must always be allowed.

## Benchmark required for promotion
- v062 benchmark gate must pass
- v066 self-map must report real_hardware_enabled: false

## Blockers
- Requires robot command schema definition.
- Requires simulation world model.
- v071 safety spine must exist before any real movement.

## Connection to v056-v066
- v062 growth streams includes robot_simulation_results.
- v066 self-map reports robot_bridge: planned.
