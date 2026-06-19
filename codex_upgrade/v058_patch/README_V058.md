# Nova Creature v058 — Dictionary to Transformer Learning Bridge

This patch makes approved dictionary entries teach the role-brain training system.

## Why

Dictionary memory is immediate.  
Transformer memory requires fine-tuning.

v058 bridges those two:

```text
approved_answer_dictionary.json
-> role lesson export
-> exports/v053_training_sets/*.json
-> v054 role checkpoint builder
-> v055 fine-tuning
```

## Apply

```bash
python scripts/apply_v058_dictionary_to_transformer.py --project-root .
python scripts/check_v058_dictionary_to_transformer.py
python scripts/v058_gold_dictionary_to_transformer_test.py
```

## Export dictionary lessons

```bash
python scripts/v058_export_dictionary_to_training.py
```

After export, run the existing training path:

```bash
python scripts/v054_role_checkpoint_builder.py
python scripts/v055_cloud_finetune_ready.py
```

If the real v055 fine-tune runner exists:

```bash
python scripts/v055_finetune_role_brains.py
```
