# v071 — Robot Safety Spine

## Purpose
Safety layer that must approve any future physical movement. Default: physical_movement_allowed: false.

## Files to create later
- src/v071_robot_safety_spine.py
- scripts/check_v071_robot_safety_spine.py

## Safety rules
- emergency_stop_available: required
- collision_check_available: required
- human_distance_check_available: required
- battery_check_available: required
- command_speed_limit: required
- movement_zone_defined: required
- real_hardware_config_present: required
- simulation_passed: required
- manual_owner_approval_required: required

Only allow real movement if all requirements are met.

## Benchmark required for promotion
- v062 benchmark gate must pass
- v066 self-map must report all safety checks

## Blockers
- Requires v070 robot sim bridge.
- Hardware config not present yet.

## Connection to v056-v066
- v066 self-map reports safety_spine: required.
