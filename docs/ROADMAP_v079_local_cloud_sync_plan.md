# v079 — Local + Cloud Sync Plan

## Purpose
Plan for syncing Nova's brain state between local and cloud versions. Checkpoint sync, memory sync, training data sync.

## Files to create later
- src/v079_sync_plan.py
- scripts/v079_sync_status.py

## Safety rules
- Do not overwrite cloud checkpoint with older local version without check.
- Must verify checkpoint hash before sync.
- Must backup before overwrite.

## Benchmark required for promotion
- v062 benchmark gate must pass

## Blockers
- Requires cloud storage configuration.
- Requires checkpoint hash verification.

## Connection to v056-v066
- v059 checkpoint resolver provides version info for sync decisions.
