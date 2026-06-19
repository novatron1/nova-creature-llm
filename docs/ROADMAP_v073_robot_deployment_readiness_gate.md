# v073 — Robot Deployment Readiness Gate

## Purpose
Final gate before any real robot movement. Checks all prerequisites: safety spine, sensors, simulation, owner approval.

## Files to create later
- src/v073_robot_deployment_readiness_gate.py
- scripts/check_v073_robot_deployment_readiness_gate.py

## Safety rules
- Must check every safety requirement before allowing movement.
- Must block deployment if any requirement is missing.
- Must report exact blockers.

## Benchmark required for promotion
- v062 benchmark gate must pass
- v071 safety spine must pass
- v072 sensor registry must report needed sensors

## Blockers
- Real hardware not available.
- Safety spine not yet installed.
- Owner approval not yet given.

## Connection to v056-v066
- v066 self-map reports conditions for real movement.
