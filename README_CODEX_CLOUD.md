# Nova Creature Codex Cloud Catch-Up v049–v055

This zip is for the **cloud Codex version** of Nova Creature.

It is **not** for the Windows laptop folder.

## Purpose

Catch the separate cloud Codex Nova project up to the same architecture that was proven locally:

- v049 multi-brain slots
- v050 router
- v051 app/chat adapter
- v052 role-brain behavior layers
- v053 training prep/export
- v054 role checkpoint builder
- v055 fine-tune trainer path

## Codex instruction

Extract this zip into the cloud Codex workspace or upload it to Codex.

Then tell Codex:

> Use `codex_upgrade/scripts/apply_codex_catchup.py` to merge this upgrade into the current cloud project root. Do not reference my Windows C drive. Treat this as its own cloud project.

## Cloud apply command

From the project root:

```bash
python codex_upgrade/scripts/apply_codex_catchup.py --project-root .
python scripts/check_codex_brain_stack.py
```

## Important

If the cloud repo does not have a `.pt` checkpoint yet, this package still creates the architecture, slot configs, lesson folders, and training pipeline. It will mark checkpoints as `missing_checkpoint_placeholder` until a checkpoint exists.

## After apply

Try:

```bash
python src/v052_role_brain_router.py --prompt "What is 12 times 12Who created youGive me the next build planImagine the brain architectureWhat is my favorite color"
```

Expected routes:

- math → left_hemisphere
- creator identity → memory_transformer
- planning → planner_transformer
- imagination → right_hemisphere
- unknown fact → critic_conscience_transformer
