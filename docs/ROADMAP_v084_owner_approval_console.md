# v084 — Owner Approval Console

## Purpose
Console for owner to review and approve pending memory items, training candidates, robot commands, and system changes.

## Files to create later
- src/v084_owner_approval_console.py
- scripts/v084_console.py

## Safety rules
- Only owner can approve.
- Pending items must be clearly displayed with context.
- Approved items must be logged.

## Benchmark required for promotion
- v062 benchmark gate must pass

## Blockers
- Requires v060 pending approval memory.
- Requires v064 approval constitution.
- Requires owner authentication mechanism.

## Connection to v056-v066
- v060 smart memory creates pending_approval items.
- v064 approval constitution defines what needs approval.
