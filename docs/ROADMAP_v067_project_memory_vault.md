# v067 — Project Memory Vault

## Purpose
Dedicated storage for project build status, version history, patch logs, test outcomes, and checkpoint metadata. Separate from conversation memory.

## Files to create later
- src/v067_project_memory_vault.py
- scripts/check_v067_project_memory_vault.py
- data/project_vault/

## Safety rules
- Do not store unapproved personal facts in project vault.
- Do not overwrite vault entries without backup.
- Vault is not trainable — it is reference-only for the router and capability answerer.

## Benchmark required for promotion
- v062 benchmark gate must pass
- v059 router must still select v055

## Blockers
- v066 capability self-map must exist first (done).
- Requires v064 memory law to filter what goes into vault.

## Connection to v056-v066
- v056 conversation memory → refers to vault for project facts
- v060 smart memory capture → project facts flow into vault
- v061 learning loop → reads vault for project status
- v066 self-map → includes vault as memory system
