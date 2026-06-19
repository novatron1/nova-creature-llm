# v083 — Capability-Aware Response Mode

## Purpose
Nova automatically checks its self-map before answering. If asked about a capability that does not exist, Nova must say it does not exist instead of hallucinating.

## Files to create later
- src/v083_capability_aware_response.py
- scripts/check_v083_capability_aware_response.py

## Safety rules
- Must not claim uninstalled capabilities.
- Must use v066 self-map as ground truth.

## Benchmark required for promotion
- v062 benchmark gate must pass
- v066 capability self-map must be active

## Blockers
- Requires v066 capability self-map.
- Requires v066 capability answerer.

## Connection to v056-v066
- v066 self-map is the ground truth for capabilities.
- v066 capability answerer provides natural language responses.
