# Nova Companion 768d Unknown-Token Rescue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce `<unk>` exposure in the Nova Companion 768d concept continuation while preserving the 5,000-token checkpoint contract.

**Architecture:** Add a pure tokenizer utility that rescues representable unknown segments and a vocabulary-migration utility that appends missing concept words without renumbering old IDs. The continuation runner uses the migrated tokenizer/model pair for coverage checks and training tensors; unresolved cases remain visible in the report.

**Tech Stack:** Python, pytest, PyTorch, Kaggle continuation runner.

**Spec:** `docs/superpowers/specs/2026-08-22-nova-companion-768d-unk-rescue-design.md`

## Global Constraints

- Keep the original checkpoint untouched; only the continuation candidate may expand vocabulary.
- Never invent token IDs; only use IDs exposed by the restored tokenizer.
- Preserve the original base and canonical checkpoints.
- Use the same rescued encoding for audit and training.

---

### Task 1: Add tokenizer rescue utility

**Files:**
- Modify: `tools/companion_768d_token_utils.py`
- Test: `tests/test_companion_768d_unk_rescue.py`

**Interfaces:**
- Produces `encode_with_unknown_fallback(text, tokenizer) -> tuple[list[int], dict]`.
- The report contains `original_unknown_count`, `rescued_count`, `unresolved_count`, and `used_fallback`.

- [ ] **Step 1: Write the failing tests**

Add tests for a known character-piece tokenizer: an unknown word is decomposed
into known pieces, known text is unchanged, and an unrepresentable symbol is
reported unresolved.

- [ ] **Step 2: Run the focused tests and confirm the expected failure**

Run: `python -m pytest tests/test_companion_768d_unk_rescue.py -q`

Expected: FAIL because `encode_with_unknown_fallback` does not exist.

- [ ] **Step 3: Implement the minimal rescue helper**

Discover token strings from `tokens`, `itos`, or `vocab`; build a longest-match
map; split whitespace-delimited segments; replace a segment only when every
piece is an exact known token and no unknown ID remains.

- [ ] **Step 4: Run the focused tests and confirm they pass**

Run: `python -m pytest tests/test_companion_768d_unk_rescue.py -q`

Expected: all focused rescue tests pass.

### Task 2: Wire the Kaggle runner to rescued encodings

**Files:**
- Modify: `.tmp_kaggle_fix/pulled_v2/nova-companion-768d-concept-upgrade.py`
- Modify: `tests/test_companion_768d_kaggle_upgrade.py`

**Interfaces:**
- `_encode_documents` uses the rescue helper before calculating coverage.
- `_tokenize_documents` uses the same rescued IDs and does not reintroduce the
  original `<unk>` encoding.

- [ ] **Step 1: Add a runner-wiring regression test**

Assert that the runner imports the rescue helper and calls it from both the
coverage and sequence paths.

- [ ] **Step 2: Run the regression test and confirm it fails**

Run: `python -m pytest tests/test_companion_768d_kaggle_upgrade.py -q`

Expected: FAIL because the runner still calls `tokenizer.encode` directly.

- [ ] **Step 3: Wire one shared encoding path**

Import `encode_with_unknown_fallback`, use it in coverage auditing, store
rescued IDs per document, and pass those IDs into tensor construction while
preserving EOT boundaries and loss-mask alignment.

- [ ] **Step 4: Run all companion tests**

Run: `python -m pytest tests/test_companion_768d_kaggle_upgrade.py tests/test_companion_768d_unk_rescue.py tests/test_companion_768d_concept_corpus.py -q`

Expected: all companion tests pass.

### Task 3: Add vocabulary migration

**Files:**
- Create: `tools/companion_768d_vocab_migration.py`
- Test: `tests/test_companion_768d_vocab_migration.py`

**Interfaces:**
- Produces `extend_tokenizer_state(tokenizer_state, additions) -> dict`.
- Produces `copy_vocab_expanded_state(source_state, target_state, old_vocab) -> dict`.

- [ ] **Step 1: Write failing migration tests**

Test deterministic append-only token IDs and exact preservation of old rows in
both embedding-shaped and output-shaped tensors.

- [ ] **Step 2: Run the migration tests and confirm they fail**

Run: `python -m pytest tests/test_companion_768d_vocab_migration.py -q`

Expected: FAIL because the migration module does not exist.

- [ ] **Step 3: Implement append-only tokenizer and state migration**

Reject duplicate/special additions, append new tokens to `tokens`, and copy
every matching old tensor into the expanded target tensor. Fail closed on an
unexpected shape change.

- [ ] **Step 4: Run migration tests and confirm they pass**

Run: `python -m pytest tests/test_companion_768d_vocab_migration.py -q`

Expected: all migration tests pass.

### Task 4: Wire migration into the Kaggle runner

**Files:**
- Modify: `.tmp_kaggle_fix/pulled_v2/nova-companion-768d-concept-upgrade.py`
- Modify: `tests/test_companion_768d_kaggle_upgrade.py`

- [ ] **Step 1: Add a runner migration-wiring regression test**

Assert that the runner collects missing tokenizer pieces, expands the config,
instantiates the expanded model, and copies the old state before training.

- [ ] **Step 2: Run it and confirm it fails**

Run: `python -m pytest tests/test_companion_768d_kaggle_upgrade.py -q`

Expected: FAIL because the runner still hard-checks a 5,000-token model.

- [ ] **Step 3: Implement controlled migration**

Add `NOVA_VOCAB_MODE=concept_expand`, collect missing tokens from concept
documents, extend tokenizer state, update `config.vocab_size`, instantiate the
expanded model, and copy the old state with the migration helper.

- [ ] **Step 4: Run all companion tests**

Run: `python -m pytest tests/test_companion_768d_kaggle_upgrade.py tests/test_companion_768d_unk_rescue.py tests/test_companion_768d_vocab_migration.py tests/test_companion_768d_concept_corpus.py -q`

Expected: all companion tests pass.

### Task 5: Build the Kaggle bundle and run a bounded rescue audit

**Files:**
- Modify: `artifacts/companion_768d_canonical_upgrade_bundle/`
- Create: `artifacts/companion_768d_unk_rescue_bundle.zip`

- [ ] **Step 1: Build the updated bundle**

Copy the runner, utility, concept data, canonical consolidation data, and a
manifest with `NOVA_UNK_POLICY=fallback` and a separate output directory.

- [ ] **Step 2: Run a bounded Kaggle audit/continuation**

Start from the verified canonical candidate, keep the original base untouched,
and run a short continuation that prints before/after unknown counts before
committing to a longer training run.

- [ ] **Step 3: Verify the candidate**

Run the deterministic concept suite plus unknown-token coverage checks. Keep the
rescue candidate only if known answers remain stable and the report shows actual
rescues; otherwise retain the prior canonical candidate and report the hard
tokenizer limit.
