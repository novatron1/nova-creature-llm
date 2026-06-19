# Local/Cloud Sync Rules (v079)

## Principle

Prevent cloud Nova and local Nova from drifting apart.

## Never Sync
- checkpoints/base/creature_v032_bigfit_twenty_plain.pt
- checkpoints/base/creature_v019_proof_fallback.pt
- checkpoints/brain_slots/*/*_v054_specialized.pt
- checkpoints/brain_slots/*/*_v055_finetuned.pt
- data/owner_approval/
- backups/
- .git/
- __pycache__/
- *.pyc

## Approval Required Before Sync
- checkpoints/
- data/smart_memory/
- data/dictionary_memory/
- data/training_data/
- data/mistake_memory/

## Cloud-Only Rules
- No local laptop access assumed.
- No Windows paths.
- No .bat files.
- Create a sync plan only — do not move or delete files.
- Report what would need to be exported for local use.

## Sync Candidate Report
The following files are candidates for export to a local Nova instance:

1. reports/v059_live_router_checkpoint_priority.json
2. reports/v062_benchmark_report.json
3. reports/v066_capability_self_map_status.json
4. reports/v075_benchmark_dashboard_status.json
5. reports/v095_intelligence_benchmark_status.json

## Version Stack
The cloud project has versions v056 through v095 installed.
