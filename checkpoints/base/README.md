# Base Checkpoints

Place the real trained checkpoint file here:

```
checkpoints/base/creature_v032_bigfit_twenty_plain.pt
```

The v054 role checkpoint builder searches for checkpoints in this priority order:

1. `checkpoints/base/creature_v032_bigfit_twenty_plain.pt`
2. `checkpoints/experimental/creature_v032_bigfit_twenty_plain.pt`
3. Any other `.pt` file under `checkpoints/` (excluding v054/v055 output files)

Once a real checkpoint exists here, run:

```bash
python scripts/v054_role_checkpoint_builder.py
```

This will produce real role-specialized checkpoint files in `checkpoints/brain_slots/*/`.
