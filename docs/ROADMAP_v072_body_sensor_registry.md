# v072 — Body Sensor Registry

## Purpose
Registry of all connected sensors: camera, microphone, speaker, LIDAR, battery, IMU. Reports which sensors are connected, which are active, and which are missing.

## Files to create later
- src/v072_body_sensor_registry.py
- scripts/check_v072_body_sensor_registry.py

## Safety rules
- Sensor status must be accurately reported — no pretending sensors exist.
- Sensor data must not be exported without approval.

## Benchmark required for promotion
- v062 benchmark gate must pass

## Blockers
- Requires physical sensor connection or simulator.
- v071 safety spine must exist.

## Connection to v056-v066
- v066 self-map includes sensor status section.
