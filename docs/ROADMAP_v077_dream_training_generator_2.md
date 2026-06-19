# v077 — Dream Training Generator 2.0

## Purpose
Enhanced dream training generator that creates more diverse practice scenarios from approved lessons. Builds on v063 dream replay.

## Files to create later
- src/v077_dream_training_generator.py
- scripts/check_v077_dream_training_generator.py

## Safety rules
- All dreams must pass critic review before training.
- Distorted dreams must be rejected.
- Do not train raw (unapproved) dream lessons.

## Benchmark required for promotion
- v062 benchmark gate must pass
- v063 dream critic must be active

## Blockers
- Requires v063 dream replay and critic.

## Connection to v056-v066
- v063 provides base dream replay.
- v061 learning loop exports approved dreams.
