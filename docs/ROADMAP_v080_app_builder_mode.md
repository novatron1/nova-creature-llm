# v080 — App Builder Mode

## Purpose
Nova can scaffold new applications using templates. Builds on v069 self-scripting.

## Files to create later
- src/v080_app_builder.py
- scripts/v080_app_builder_demo.py

## Safety rules
- App scaffolding must go into sandbox/generated_scripts/ or dedicated export folder.
- Do not overwrite existing app files.
- Do not install packages without approval.

## Benchmark required for promotion
- v062 benchmark gate must pass
- v069 self-scripting must be active

## Blockers
- Requires v069 self-scripting brain.

## Connection to v056-v066
- v065 skill hands provides write permissions.
- v069 self-scripting brain provides script generation.
