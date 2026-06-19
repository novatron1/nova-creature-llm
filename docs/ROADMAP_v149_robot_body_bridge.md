# v149 — Robot Body Bridge Roadmap

## Purpose
Prepare Nova for a physical robot body while keeping all movement simulation-only.

## Existing Robot Stack (v070-v107)
- v070: robot command schema + simulation bridge
- v071: robot safety spine
- v072: body sensor registry
- v073: robot deployment readiness gate
- v074: mistake memory
- v101: hardware config reader
- v102: emergency stop verifier
- v103: sensor feedback loop
- v104: safe movement zone mapper
- v105: robot simulation benchmark
- v106: manual owner approval gate
- v107: limited real-world movement readiness test

## Rules
- real_hardware_enabled: False by default
- movement blocked unless all safety systems pass
- owner approval required before any real movement
- emergency stop must be verified
- simulation benchmark must pass

## Prerequisites for Real Movement
1. hardware config present and validated
2. emergency stop verified functional
3. sensor feedback loop connected
4. safe movement zone mapped
5. simulation benchmark all passing
6. owner approval granted explicitly
7. movement readiness test passes

## Files to Create Later
- `src/v149_robot_bridge_controller.py`
- `scripts/check_v149_robot_bridge.py`
- `data/robot/bridge_status.json`
- `data/robot/movement_log.jsonl`
