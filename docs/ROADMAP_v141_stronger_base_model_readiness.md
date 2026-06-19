# v141 — Stronger Base Model Readiness

## Purpose
Prepare Nova Creature to swap or load a stronger base model without breaking the brain architecture.

## Current Base
- v032: base checkpoint (preserved)
- v019: fallback checkpoint (preserved)
- v054: role checkpoints (preserved)
- v055: fine-tuned role checkpoints (live)

## Future Base Requirements
- new base model must pass all v095 intelligence benchmarks
- new base model must not break v059 router
- new base model must not break v061 learning loop
- new base model must not break v066 self-map
- new base model must support current tokenizer or provide compatible mapping

## Files to Create Later
- `src/v141_base_model_loader.py` — load and validate new base
- `scripts/check_v141_base_model.py` — compatibility checker
- `data/base_model/compatibility_report.json`

## Compatibility Blockers
- vocabulary mismatch
- tokenizer mismatch
- hidden size mismatch
- missing role heads
- benchmark regression

## Safety Rules
- never delete v032 or v019 fallback
- never delete v054 or v055 checkpoints
- benchmark before and after swap
- rollback if regression detected
