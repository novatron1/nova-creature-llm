# v058 Dictionary to Transformer Learning

v057 made dictionary memory answer immediately.

v058 makes the transformer able to learn from the dictionary by exporting approved dictionary entries into role-brain training sets.

## Flow

```text
approved_answer_dictionary.json
-> classify dictionary entry by role
-> exports/v053_training_sets/<role>_training_set.json
-> v054 role checkpoint builder
-> v055 fine-tune
```

## Commands

```bash
python scripts/check_v058_dictionary_to_transformer.py
python scripts/v058_export_dictionary_to_training.py
python scripts/v054_role_checkpoint_builder.py
python scripts/v055_cloud_finetune_ready.py
```

If actual v055 fine-tuning is implemented:

```bash
python scripts/v055_finetune_role_brains.py
```
