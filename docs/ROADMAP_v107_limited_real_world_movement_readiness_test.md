# V107 Limited Real World Movement Readiness Test

## Purpose
Tests all safety prerequisites. If pass, allows limited real movement.

## Files to create later
- src/v107_limited_real_world_movement_readiness_test.py
- scripts/check_v107_limited_real_world_movement_readiness_test.py
- scripts/v107_limited_real_world_movement_readiness_test_demo.py

## Safety rules
- All robot-related work must remain simulation-only unless safety spine, emergency stop, and owner approval exist.
- Do not train uncertain/speculative memory.
- Do not modify core files without backup.
- Do not access real hardware unless all safety gates pass.
- Visual/vision work requires screenshot capture capability (not yet installed).

## Benchmark required for promotion
- v095 intelligence benchmark suite must pass (13/13).
- No regression in v059/v061/v066/v080.

## Blockers
- Requires v095+ base with passing benchmarks.
- Vision versions (v096-v100) require screenshot/vision input capability.
- Robot versions (v101-v107) require physical hardware verification.
- Autonomy versions (v108-v114) require stable base.
- Business versions (v115-v120) require app/game builder approval.

## Connection to existing stack
- v056-v066: Base memory, learning, and capabilities.
- v069: Self-scripting for sandbox scripts.
- v080: App builder mode for project scaffolding.
- v086-v095: Intelligence stack for reasoning and benchmark verification.
