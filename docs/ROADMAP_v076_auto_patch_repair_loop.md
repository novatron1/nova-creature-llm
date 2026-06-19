# v076 — Auto Patch Repair Loop

## Purpose
When a test or benchmark fails, Nova can attempt to diagnose and repair the issue automatically.

## Files to create later
- src/v076_auto_patch_repair.py
- scripts/check_v076_auto_patch_repair.py

## Safety rules
- Must create backup before any patch.
- Must verify patch with tests.
- Must rollback if patch fails.

## Benchmark required for promotion
- v062 benchmark gate must pass
- Auto-patch must not degrade any existing benchmark

## Blockers
- Requires v069 self-scripting brain.
- Requires v062 benchmark gate.

## Connection to v056-v066
- v065 skill hands provides file operations.
- v069 self-scripting brain writes patches.
