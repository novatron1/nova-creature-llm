# Nova Companion 768d Concept Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and launch a safe dictionary/concept continuation stage for the Nova Companion 768d Kaggle model.

**Architecture:** A pure-stdlib corpus builder converts dictionary entries and curated relationships into weighted text records compatible with the existing causal-LM input. A separate Kaggle runner loads the base checkpoint and frozen tokenizer, applies answer-span loss masks, mixes concept data with sampled replay, and writes to a new resumable run directory.

**Tech Stack:** Python 3.10+, JSONL, PyTorch, Kaggle CLI, pytest.

**Spec:** `docs/superpowers/specs/2026-08-21-nova-companion-768d-concept-upgrade-design.md`

## Global Constraints

- Preserve the 768d model architecture and 5,000-token vocabulary.
- Never overwrite the base run directory or base checkpoint.
- Never silently accept concept rows that encode to `<unk>`.
- Report unknown-token coverage truthfully even when the selected run keeps those rows.
- Mask prompt/header tokens so optimization concentrates on answer and relation text.
- Keep the current atomic checkpoint and stop-signal behavior.
- Keep sealed evaluation data out of training.

### Task 1: Corpus builder and tests

**Files:**
- Create: `tools/build_companion_768d_concept_corpus.py`
- Create: `tests/test_companion_768d_concept_corpus.py`
- Create: `data/companion_768d_concept_relations.json`

**Interfaces:**
- `build_concept_records(dictionary_path, relations_path) -> list[dict[str, str]]`
- `mix_replay_records(concept_records, replay_records, concept_ratio, seed) -> list[dict[str, str]]`
- `token_coverage(texts, tokenizer_tokens) -> dict[str, object]`
- CLI writes `train.jsonl`, `validation.jsonl`, `concept_eval.jsonl`, and `manifest.json`.

**TDD steps:**
- [ ] Write failing tests for multi-view records, deterministic splits, replay ratio, and unknown-token reporting.
- [ ] Run the focused tests and confirm failure because the builder does not exist.
- [ ] Implement the minimal builder and curated relationship file.
- [ ] Run the focused tests and confirm they pass.

### Task 2: 768d continuation runner

**Files:**
- Create: `.tmp_kaggle_fix/pulled_v2/nova-companion-768d-concept-upgrade.py`
- Create: `tools/prepare_companion_768d_kaggle_upgrade.py`
- Create: `tests/test_companion_768d_kaggle_upgrade.py`

**Interfaces:**
- Environment variables: `NOVA_DATA_ROOT`, `NOVA_CONCEPT_ROOT`, `NOVA_BASE_CHECKPOINT`, `NOVA_RUN_DIR`, `NOVA_MAX_STEPS`, `NOVA_CONCEPT_RATIO`, `NOVA_LEARNING_RATE`.
- Runner loads `NOVA_BASE_CHECKPOINT`, validates the saved tokenizer against the active tokenizer, resets optimizer state, and trains the mixed corpus.
- Preparation tool writes a Kaggle-ready bundle and `run_manifest.json` without changing the base checkpoint.

**TDD steps:**
- [ ] Write failing tests for missing base checkpoint, tokenizer mismatch, separate run directory, and required environment manifest.
- [ ] Run the focused tests and confirm failure.
- [ ] Implement the continuation runner and bundle preparation tool.
- [ ] Run the focused tests and confirm they pass.

### Task 3: Build artifact and run locally

**Files:**
- Create: `artifacts/companion_768d_dictionary_upgrade/` (generated, ignored if appropriate)
- Create: `reports/companion_768d_dictionary_upgrade_manifest.json`

**Steps:**
- [ ] Build the concept corpus from `data/builtin_word_dictionary.json`.
- [ ] Run coverage and schema validation against the generated files.
- [ ] Run the runner in dry-run mode against a fake checkpoint metadata fixture; do not start a full local 768d training job without the Kaggle input dataset.

### Task 4: Kaggle launch

**Steps:**
- [ ] Check Kaggle CLI authentication and notebook permissions.
- [ ] Push or create only the upgrade bundle required by the approved private Kaggle workflow.
- [ ] Launch the 768d concept continuation with a new run directory.
- [ ] Capture the Kaggle run identifier/status and report any external blocker accurately.

### Task 5: Focused answer-training correction

**Files:**
- Modify: `tools/build_companion_768d_concept_corpus.py`
- Modify: `.tmp_kaggle_fix/pulled_v2/nova-companion-768d-concept-upgrade.py`
- Modify: `tools/companion_768d_token_utils.py`
- Test: `tests/test_companion_768d_concept_corpus.py`
- Test: `tests/test_companion_768d_kaggle_upgrade.py`

**Interfaces:**
- `build_weighted_focus_records(records) -> list[dict[str, str]]` repeats question/answer and reasoning views deterministically without changing source facts.
- `tokenize_documents_with_boundaries(documents, tokenizer) -> list[int]` emits one EOT ID after every record.
- `build_loss_mask(text, tokenizer) -> list[int]` returns zero for prompt/header tokens and one for answer/statement tokens.

**Steps:**
- [ ] Write failing tests for deterministic focus weighting and prompt-versus-answer mask alignment.
- [ ] Run the focused tests and confirm the new behavior fails.
- [ ] Implement weighted records and masked causal loss with replay ratio 0.35, learning rate 2e-6, and a separate run directory.
- [ ] Run all focused tests and compile checks.
- [ ] Publish the corrected bundle and run the focused continuation from the untouched original `final.pt`.
- [ ] Evaluate exact answers before EOT and retain both original and candidate outputs until the candidate passes regression checks.
