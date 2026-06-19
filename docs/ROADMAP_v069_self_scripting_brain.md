# v069 — Self-Scripting Brain

## Purpose
Nova can write, test, repair, and report scripts inside a safe sandbox. Generated scripts go into sandbox/generated_scripts/.

## Files to create later
- src/v069_self_scripting_brain.py
- scripts/v069_self_script_demo.py
- sandbox/generated_scripts/

## Safety rules
- Generated scripts must go into sandbox/generated_scripts/ only.
- Do not overwrite app files directly.
- Do not run dangerous shell commands.
- Do not delete files.
- Do not install packages unless explicitly approved.
- Every script must have a test.
- Every script must produce a report.

## Benchmark required for promotion
- v062 benchmark gate must pass
- Self-scripting sandbox must not escape project root

## Blockers
- Requires sandbox folder (sandbox/generated_scripts/).
- Requires code execution sandboxing.

## Connection to v056-v066
- v065 skill hands provides read/write permission model.
- v066 self-map can report self-scripting capability.
