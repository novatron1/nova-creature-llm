# v074 — Mistake Memory / Error Bank

## Purpose
Track mistakes, errors, and failures so Nova can learn from them. Error patterns can become training data.

## Files to create later
- src/v074_error_bank.py
- scripts/check_v074_error_bank.py
- data/error_bank/

## Safety rules
- Do not store personal data in error bank.
- Error patterns that repeat should become training candidates.
- Error bank items must pass v064 memory law before training.

## Benchmark required for promotion
- v062 benchmark gate must pass

## Blockers
- Requires v064 memory law to filter what goes into error bank.

## Connection to v056-v066
- v062 growth streams includes error_reports.
- v061 learning loop can use error patterns as training candidates.
