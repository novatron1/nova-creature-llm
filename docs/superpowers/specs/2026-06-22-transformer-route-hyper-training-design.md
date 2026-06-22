# Transformer Route Hyper-Training Design

## Purpose

Repair Nova's real transformer route, train route selection and role-specific answer generation together, and prove improvement with held-out tests before any candidate checkpoint becomes live.

This work is successful only when the application can produce verified transformer-sourced responses through real role checkpoints. Dictionary hits, memory recalls, fallback templates, changed checkpoint hashes, and predetermined score reports do not count as proof that transformer learning works.

## Current State

The repository currently contains a hybrid router, a NumPy transformer implementation, role-specific training sets, conversation data, historical reports, and training entry points. The inspected local state also contains these blockers:

1. The local checkout has no `checkpoints/` directory, so none of the seven transformer roles can load.
2. Python 3.11 is installed, but NumPy and PyTorch are not installed in the active interpreter.
3. `NovaTransformer.generate()` in `src/nova_transformer_engine.py` returns `(text, stats)`, while `src/nova_hybrid_router.py` treats the return value as a string.
4. Checkpoint selection is fragmented across multiple modules and does not consistently prioritize a verified trained candidate.
5. The NumPy fallback in `src/v055_assisted_learning_bridge.py` applies deterministic noise to weights. A changed hash proves changed bytes, not learned behavior.
6. The PyTorch training branch in `run_finetune()` is unreachable when PyTorch is available because the function does not continue into the gradient-training implementation.
7. Conversation training data contains recursive follow-up responses such as repeated “I recall your last question,” which must not be learned.
8. Recent route logs contain dictionary, memory, and fallback routes, but no proven transformer route.
9. Historical reports show useful prior milestones, but some older score scripts use fixed values rather than measurements from live checkpoints.

The last recorded data remains part of the comparison history:

- Historical hybrid test: 20/20
- Historical dictionary jump: 11/11
- Recent route traces inspected: 25
- Dictionary routes: 11
- Memory routes: 3
- Fallback routes: 11
- Proven transformer routes: 0
- Conversation examples parsed: 404
- Known recursive/repetitive outputs: 11
- Role training-set counts:
  - critic conscience: 54
  - dream simulation: 15
  - left hemisphere: 192
  - memory: 373
  - planner: 66
  - right hemisphere: 94
  - speech output: 30

These numbers are historical context, not the new baseline. The implementation must measure a fresh baseline after the runtime and checkpoints are restored.

## Chosen Approach

Use a guarded dual-loop hyper-training system:

- **Loop A: Route learner** improves domain classification and ordered role selection.
- **Loop B: Role answer learners** improve answer generation for each of the seven specialized roles.
- **Promotion gate** compares the candidate against both the fresh frozen baseline and the previous accepted winner.

A candidate is promoted only when routing improves, answer quality improves, protected behavior does not regress, the saved artifacts reload successfully, and a confirmation run reproduces the result.

## Scope

### In Scope

- Restore or bootstrap real model checkpoints.
- Install and verify the local transformer runtime.
- Repair the transformer inference contract.
- Centralize promoted-checkpoint resolution.
- Replace random-noise checkpoint mutation with loss-driven training.
- Build clean, role-labeled, leak-resistant train/validation/promotion datasets.
- Train route selection and role answers.
- Add transformer-only unit, integration, reload, negative-control, and live-app tests.
- Generate machine-readable and human-readable before/after reports.
- Promote only a verified winner and preserve rollback metadata.

### Out of Scope

- Replacing the 997K-parameter architecture with a new large language model.
- Training from scratch on broad internet-scale data.
- Rewriting unrelated dictionary, people-memory, mobile, sensory, or robot systems.
- Treating dictionary or memory fast paths as transformer proof.
- Automatically downloading an unknown model from an unapproved external source.
- Promoting a checkpoint solely because its hash changed or training loss decreased.

## Architecture

### 1. Training Preflight

One preflight component owns environmental readiness.

It must:

- locate the Python executable used by Nova;
- verify required packages and versions;
- locate an approved base checkpoint source;
- verify all checkpoint files are real ZIP-based tensor archives rather than placeholders;
- validate required tensor names, shapes, dtypes, and finite values;
- verify the tokenizer vocabulary size matches the model;
- record runtime versions, checkpoint hashes, and the preflight verdict.

If no approved base checkpoint exists locally, preflight returns `BLOCKED` with exact recovery instructions. It must not manufacture a placeholder and call the system trainable.

### 2. Checkpoint Registry and Resolver

One registry becomes the source of truth for checkpoint selection.

For each role it records:

- base checkpoint;
- frozen baseline checkpoint;
- current candidate;
- promoted winner;
- rollback predecessor;
- SHA-256;
- dataset fingerprint;
- training configuration;
- measured metrics;
- promotion verdict;
- creation time.

The live resolver selects only:

1. the latest promoted winner;
2. otherwise the verified frozen baseline;
3. otherwise an approved base checkpoint.

Unverified candidates, placeholders, random-noise variants, and partially written files are never loaded by the live application.

Checkpoint writes use a temporary file followed by an atomic replace. Promotion updates the registry only after reload and benchmark checks finish.

### 3. Unified Transformer Inference Contract

All transformer generation uses one result type containing:

- `text`;
- `role`;
- `checkpoint_path`;
- `checkpoint_hash`;
- `tokens_generated`;
- `elapsed_seconds`;
- `tokens_per_second`;
- `finish_reason`;
- `error`, when applicable.

The hybrid router must not slice, measure, or concatenate a raw tuple. It consumes the normalized result object and includes its evidence in the route trace.

Generation failures are explicit. Empty, malformed, non-finite, or repetitive output is rejected before it reaches the user.

### 4. Route Learner

The route learner predicts:

- domain;
- primary role;
- ordered supporting roles;
- confidence.

Training examples come from approved route labels, protected benchmark cases, successful traces, and manually validated corrections. The existing keyword route remains the frozen baseline and emergency fallback, not the claimed learned route.

The initial implementation should use a small deterministic supervised classifier over tokenizer-derived features or transformer embeddings. It must support probability output, saved model state, and reproducible evaluation. It must not require modifying all seven language-model checkpoints merely to learn route labels.

At inference time:

1. dictionary and explicit memory commands may still use their approved fast paths;
2. transformer-eligible prompts are scored by the route learner;
3. low-confidence routing falls back safely and is logged;
4. high-confidence routing selects the primary role and optional support roles;
5. the trace identifies whether the route came from the learned classifier or the baseline fallback.

### 5. Role Answer Trainers

Each of the seven roles receives only appropriate examples:

- left hemisphere: coding, math, exact logic;
- right hemisphere: visual patterns, design, constrained creativity;
- memory transformer: identity, factual recall, names, stored knowledge;
- planner transformer: sequencing, dependencies, plans, task decomposition;
- critic conscience transformer: truth checks, uncertainty, contradictions, safety;
- dream simulation transformer: counterfactuals, simulations, scenario variants;
- speech output transformer: clarity, concise wording, explanation, final formatting.

Training examples use explicit prompt and answer boundaries. Loss is calculated on answer tokens; prompt tokens are masked from the supervised answer objective.

The trainer must provide:

- deterministic seeds;
- mini-batching;
- gradient clipping;
- configurable learning rate;
- early stopping on validation loss;
- best-validation checkpoint retention;
- finite-loss and finite-gradient guards;
- per-epoch metrics;
- cancellation without corrupting checkpoints.

The random-perturbation implementation is removed from production training. If a lightweight NumPy trainer remains, it must implement gradients tied to the measured loss. Prefer the existing PyTorch training path once repaired because it already matches the checkpoint format and provides reliable automatic differentiation.

### 6. Dataset Builder and Quality Gate

The dataset builder combines:

- approved dictionary question/answer pairs;
- clean role training sets;
- clean user/Nova exchanges;
- approved rapid-learning lessons;
- validated route corrections;
- protected benchmark cases.

It rejects or quarantines:

- malformed JSON/JSONL;
- duplicate examples;
- empty prompts or answers;
- fallback templates presented as knowledge;
- recursive follow-up chains;
- high-repetition responses;
- unsupported capability claims;
- examples with unresolved role labels;
- examples whose answer is truncated;
- test fixtures accidentally copied into training;
- conflicting answers without an approved resolution.

Every accepted example receives:

- stable ID;
- source;
- intent/paraphrase group;
- domain;
- primary role;
- support roles;
- prompt;
- answer;
- quality flags;
- approval state.

### 7. Leak-Resistant Dataset Split

The cleaned corpus is frozen into:

- 70% training;
- 15% validation;
- 15% sealed promotion test.

Rows sharing an intent, source fact, template, or paraphrase family remain in the same split. This prevents near-duplicate leakage.

Protected identity, arithmetic, safety, uncertainty, memory, and route cases are separately versioned and never trained on unless a new benchmark version is intentionally created.

The builder records a fingerprint for the cleaned corpus and each split.

### 8. Candidate Training Orchestrator

One orchestrator runs the complete experiment:

1. run preflight;
2. freeze the current baseline and registry;
3. build and fingerprint the dataset;
4. measure fresh baseline routing and answer metrics;
5. train route candidate;
6. train each role candidate;
7. reload candidates in a fresh process;
8. run validation and promotion tests;
9. run negative controls;
10. compare baseline, previous winner, and candidate;
11. promote or reject;
12. generate reports.

Failure in one role does not silently produce a partial global promotion. A joint candidate is promoted only when all required roles and the route model pass. Per-role candidate results remain available for diagnosis.

## Live Request Data Flow

1. Receive user input.
2. Check explicit commands, permissions, and approved dictionary fast path.
3. Check eligible explicit memory operations.
4. Send transformer-eligible input to the learned route model.
5. Select the promoted primary role and supporting roles.
6. Generate an answer from the primary role checkpoint.
7. Run critic checks for uncertainty, contradiction, malformed output, and unsupported claims.
8. Optionally run speech-output formatting without changing factual content.
9. Return the answer with a route trace.
10. Log outcome evidence for later review; do not automatically train on the response.

The route trace includes:

- source=`transformer`;
- route model version and hash;
- predicted domain;
- ordered roles;
- routing confidence;
- checkpoint hash for every invoked role;
- generation statistics;
- critic decision;
- fallback reason, if any.

## Training Data Flow

1. Ingest approved sources.
2. Normalize records.
3. quarantine low-quality or conflicting examples.
4. label domain and roles.
5. group paraphrase families.
6. freeze train, validation, and promotion splits.
7. fingerprint datasets.
8. train route and answer candidates.
9. evaluate without exposing promotion data to training.
10. save candidates separately from live winners.
11. promote atomically only after all gates pass.

## Evaluation

### Fresh Baseline

After checkpoints and dependencies are restored, run the full proof suite against the frozen pre-training model. This becomes the authoritative baseline. Historical report values remain visible but are not substituted for fresh measurements.

### Routing Score: 50%

Routing uses:

- domain accuracy;
- primary-role macro F1;
- ordered full-path correctness;
- confidence calibration;
- transformer eligibility accuracy;
- unnecessary fallback rate.

Macro F1 is required so the large memory dataset cannot hide poor dream, critic, planning, or speech routing.

### Answer Score: 40%

Answer quality uses:

- held-out answer-token loss;
- normalized exact or token F1 match where appropriate;
- protected factual test accuracy;
- task-specific correctness for coding, math, planning, and critic cases;
- semantic similarity for acceptable open-form answers;
- unsupported-claim rate;
- malformed-output rate;
- repetition rate.

Semantic similarity is supportive evidence, not permission to pass factually incorrect answers.

### Stability Score: 10%

Stability uses:

- checkpoint reload success;
- deterministic confirmation-run agreement;
- finite output and finite logits;
- latency ceiling;
- no increase in crashes;
- existing memory, dictionary, permission, and launcher regression tests;
- live application smoke test.

### Joint Score

`joint = 0.50 * routing + 0.40 * answers + 0.10 * stability`

All component scores are normalized to 0–100 and their raw submetrics remain in the report.

## Promotion Rules

A candidate is promoted only when all conditions are true:

1. joint score improves by at least 2.0 points over the stronger of the fresh baseline or previous winner, or reaches at least 95.0 without regression;
2. primary-role macro F1 improves;
3. answer composite improves;
4. no protected domain metric falls by more than 1.0 point;
5. protected identity, arithmetic, safety, uncertainty, and memory tests remain perfect;
6. malformed output does not increase;
7. repetition does not increase and is below 2%;
8. all seven role checkpoints load with valid tensors;
9. route model and role checkpoints reload in a fresh process;
10. a deterministic confirmation run reproduces the verdict;
11. the live application smoke test uses transformer routes for representative coding, planning, critic, creative, memory, and speech prompts;
12. the complete regression suite passes.

If any rule fails, the verdict is `REJECTED` and the current live winner remains unchanged.

If preflight cannot obtain approved checkpoints or the runtime cannot be prepared, the verdict is `BLOCKED`, not `FAILED` or `PROMOTED`.

## Proof Suite

### Preflight Tests

- Python version is supported.
- Required packages import.
- Seven approved role checkpoints exist.
- No checkpoint is a placeholder.
- Tensor names and shapes match the architecture.
- Tokenizer and checkpoint vocabulary sizes match.

### Route Unit Tests

- every domain has held-out positive cases;
- overlapping-keyword cases select the expected primary role;
- paraphrases route consistently;
- low-confidence cases fall back explicitly;
- macro F1 and confusion matrix are generated.

### Transformer-Only Integration Tests

Dictionary and memory shortcuts are disabled for this suite.

Every passing case must show:

- `source == "transformer"`;
- learned route-model evidence;
- a selected promoted role;
- checkpoint hash;
- nonempty generated output;
- finite generation statistics;
- no fallback template.

### Answer Tests

- exact protected facts;
- coding and math correctness;
- planning completeness and order;
- critic uncertainty and contradiction handling;
- creative constrained-generation checks;
- memory recall;
- speech clarity;
- repetition and malformed-output detection.

### Negative Controls

The suite must fail when:

- route labels are deliberately shuffled;
- a checkpoint is absent;
- a placeholder checkpoint is supplied;
- random-noise weights are used as a candidate;
- promotion data leaks into training;
- generation returns an empty or repetitive result;
- the router reports transformer source without checkpoint evidence.

These controls prove that the evaluator can reject false progress.

### Reload Test

Start a fresh process, reload the saved candidate, verify hashes, and rerun a representative metric subset. The verdict must agree within the configured deterministic tolerance.

### Live App Smoke Test

Exercise the server entry point with representative prompts for coding, planning, critic, creative, memory, and speech. Each must produce a transformer route trace unless an intentional approved fast path applies.

## Error Handling

- Missing dependency: stop at preflight with the package and interpreter path.
- Missing checkpoint: stop at preflight and name the expected approved source.
- Placeholder or malformed checkpoint: quarantine it and stop.
- Non-finite loss or gradients: abort the candidate and preserve the live winner.
- Interrupted training: delete incomplete temporary artifacts only; preserve source and live checkpoints.
- Corrupt candidate: reject during reload.
- Metric regression: reject and report affected domains/examples.
- Dataset parse error: quarantine the row with source and line number.
- Conflicting lesson: exclude until explicitly resolved.
- Low route confidence: use labeled fallback and log it; never mislabel it as transformer success.

## Reports and Artifacts

Each run creates:

- `reports/transformer_hyper_training_<run-id>.json`
- `reports/transformer_hyper_training_<run-id>.md`
- route confusion matrix data;
- per-role metric data;
- accepted and quarantined dataset manifests;
- baseline, candidate, and winner hashes;
- promotion decision;
- examples improved;
- examples regressed;
- remaining weaknesses;
- exact runtime, seed, dataset fingerprints, and duration.

The human-readable report begins with one verdict:

- `PROMOTED`
- `REJECTED`
- `BLOCKED`

It then shows historical data, fresh baseline, candidate, previous winner, deltas, and reasons.

## Acceptance Criteria

The implementation is complete when:

1. all seven real role checkpoints load locally;
2. the training runtime passes preflight;
3. the hybrid router consumes the unified transformer generation result correctly;
4. the live checkpoint resolver uses only approved baseline or promoted artifacts;
5. random-noise mutation is not used as training;
6. route and role-answer candidates train with loss-driven gradients;
7. polluted examples are quarantined;
8. the sealed promotion test remains separate from training;
9. transformer-only integration tests produce proven transformer traces;
10. negative controls fail as expected;
11. a before/after report compares historical data, fresh baseline, candidate, and winner;
12. only a candidate satisfying every promotion rule becomes live;
13. a rejected candidate leaves the live system unchanged;
14. the application smoke test proves transformer routes work after restart.
