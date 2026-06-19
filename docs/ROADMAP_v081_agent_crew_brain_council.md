# v081 — Agent Crew / Brain Organ Council

## Purpose
Brain organs vote on decisions. Each organ gets a weighted vote based on confidence. Council resolves conflicting routes.

## Files to create later
- src/v081_brain_council.py
- scripts/v081_brain_council_demo.py

## Safety rules
- Critic organ must have veto power.
- No organ can override safety limits.
- Real movement requires safety spine approval first.

## Benchmark required for promotion
- v062 benchmark gate must pass
- v059 router must still resolve correctly

## Blockers
- Requires all 7 brain organs to be active.
- Requires v059 checkpoint resolver.

## Connection to v056-v066
- v052 role brain router routes individual queries.
- v059 resolver selects active checkpoints per role.
