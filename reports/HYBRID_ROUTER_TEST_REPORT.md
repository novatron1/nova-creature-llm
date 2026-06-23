# Nova Hybrid Router — Measured Task 11 Evidence

## Date

2026-06-23

## Scope

Task 11 tested transformer-only routing, fresh-process reload/preflight, and live `/api/chat` application wiring. Earlier optimistic claims that transformer routing was proven by broad manual smoke tests have been replaced with measured evidence below.

## Historical results

- Starting head: `a0d5a8079ac9d56f3ec696449d6482a9b6628c4e` (`fix: report actual guarded training run id`).
- Baseline transformer-only integration test already passed before this task's new training run, meaning this worktree already had a live/promoted route model available.
- First full hyper-training attempt: `20260623T023139Z_4ed4b48f`, `BLOCKED`.
  - Report: `reports/transformer_hyper_training_20260623T023139Z_4ed4b48f.json`
  - Blocker: `train row 34: supervised sequence lost SEP during truncation`.
- Blocker correction: dataset builder now quarantines answer rows whose prompt cannot preserve `BOS + prompt + SEP` inside the role model block.
- Second full hyper-training attempt: `20260623T023523Z_88d9ff9e`, `REJECTED`.
  - Report: `reports/transformer_hyper_training_20260623T023523Z_88d9ff9e.json`
  - Weakest failed gate: candidate answer malformed rate was `1.0000` vs baseline `0.0000`.
- Targeted wiring correction: role candidate checkpoints now train into the checkpoint tree under `checkpoints/brain_slots/<role>/candidates/...`, preserving the existing generation evidence contract.

## Fresh baseline and final candidate run

- Final run ID: `20260623T024446Z_1b881a30`
- Verdict: `REJECTED`
- JSON report: `reports/transformer_hyper_training_20260623T024446Z_1b881a30.json`
- Markdown report: `reports/transformer_hyper_training_20260623T024446Z_1b881a30.md`
- Dataset fingerprint: `30b87406777707ad543125b95826160f7a935743949c089a35a368a9658cba41`
- Split counts: promotion `99`, train `464`, validation `97`
- Quarantine counts included:
  - `prompt_too_long_for_role_training`: `43`
  - `duplicate`: `225`
  - `high_repetition`: `212`
  - `truncated_answer`: `90`
  - `weak_route_prompt`: `17`

## Metrics

| Metric | Baseline | Candidate |
|---|---:|---:|
| Joint score | `41.74549976393295` | `40.73157879046851` |
| Route macro F1 | `63.490999527865895` | `61.46315758093702` |
| Domain accuracy | `65.65656565656566` | `71.71717171717172` |
| Answer composite | `0.0` | `0.0` |
| Malformed output rate | `0.0` | `0.0` |
| Stability score | `100.0` | `100.0` |

Final rejection reasons:

- Joint score gain `-1.01` is below `2.0`.
- Route macro F1 did not improve: `61.46 <= 63.49`.
- Answer composite did not improve: `0.00 <= 0.00`.

## Candidate and live hashes

- Final route candidate metadata model hash: `c037a3004ce455cd6463ed858640868cd7ede6605f414fb7a9e95d03dd7048b2`
- Final route candidate file hash: `8ad10abae97881508c75194ff39cb0f600ed6e893c8572cebf0801a8d3f86974`
- Existing live route model hash observed by integration/app smoke: `4d33f0df3ed4c951244b6d000648490b22bb4a791115b7606afa9484460b12db`
- Existing live checkpoint hash observed by integration/app smoke: `23363326e6561414e4ac4af92c49b9c8b16797ccada083ab89f4a8cded080c47`

Final role candidate checkpoint hashes:

- `left_hemisphere`: `409d7fc0c606688772a62ea398e5cd4572384800618c5e40ce23076718ebfec8`
- `right_hemisphere`: `4a03f188b97ee3fc907a80be25b0adeab416fe09a6c4f3ca0547b1a4c14aac39`
- `memory_transformer`: `3b99c0b52ad5fd1a3098818e115fad0907bcdbcbc13e7d27b9fc93c1d7ee4e21`
- `planner_transformer`: `149a90051f7b5892f1eabd8877186e162a9e0983a8da1d380ef58eb040e1898f`
- `critic_conscience_transformer`: `5b30ee996da8109344c8cc8ef2d21081c0119df54eec2644c4815bccffd39160`
- `dream_simulation_transformer`: `1a937430010869e82608eb04ef6b6689708c5f0660154210e64638ae6f0ff7a7`
- `speech_output_transformer`: `0defd7af9d6eff406c2841666beee5db0cef6bd1c28f0b265a4a3f7f14a79518`

## Route confusion matrix summary

Final candidate promotion split role confusions, `expected -> predicted`:

- `speech_output_transformer -> speech_output_transformer`: `35`
- `memory_transformer -> memory_transformer`: `14`
- `left_hemisphere -> left_hemisphere`: `13`
- `memory_transformer -> speech_output_transformer`: `7`
- `right_hemisphere -> right_hemisphere`: `4`
- `critic_conscience_transformer -> critic_conscience_transformer`: `3`
- `planner_transformer -> planner_transformer`: `3`
- `speech_output_transformer -> dream_simulation_transformer`: `3`
- `speech_output_transformer -> memory_transformer`: `3`
- `left_hemisphere -> planner_transformer`: `2`
- Single-count misses also remained across planning, critic, dream, coding, and memory roles.

## Transformer-only integration evidence

- Test: `py -3 -m pytest tests/test_nova_transformer_route_integration.py -q`
- Result: `1 passed`
- Prompt-level transformer-only pass count: `7/7`
- Required evidence confirmed for each prompt:
  - non-empty response;
  - `trace["source"] == "transformer"`;
  - non-empty route-model hash;
  - non-empty checkpoint hash;
  - `trace["generation"]["ok"] is True`;
  - no fallback skill.

## Fresh process preflight

- Command: `py -3 -c "import sys; sys.path.insert(0, 'src'); from nova_training_preflight import run_preflight; from pathlib import Path; print(run_preflight(Path('.'))['verdict'])"`
- Result: `READY`

## Regression and app smoke

- Full suite: `py -3 -m pytest tests -q`
- Result after Task 11 changes: `154 passed`
- App smoke:
  - Server command: `py -3 nova_enhanced_server.py 3000`
  - Request body used the required `message` field.
  - Result trace:
    - `source`: `transformer`
    - `roles`: `["left_hemisphere"]`
    - `route_model_hash`: `4d33f0df3ed4c951244b6d000648490b22bb4a791115b7606afa9484460b12db`
    - `checkpoint_hash`: `23363326e6561414e4ac4af92c49b9c8b16797ccada083ab89f4a8cded080c47`
    - both hashes matched 64-character hexadecimal format.

## Autonomous App Navigation Mode

The branch also adds the approved app-operator design and implementation. Navigation commands are recognized before generic memory/dictionary fallback and return structured traces with `source: "app_navigation"`, target surface, action, safety level, steps, and verification state.

Verified examples:

- `go to Agent Library` -> `agent_library`, `navigate`, `read_only`;
- `make an agent that researches better LLM methods weekly` -> create-agent action loop with schedule/save/verify steps;
- `check if it works` -> uses recent context;
- `delete that draft` -> blocked with `confirm_required`;
- generic chat still uses the existing transformer route path.

## Remaining weaknesses

- No new hyper-training candidate was promoted in Task 11.
- The existing live/promoted route path passes transformer-only integration and app smoke, but the fresh candidate failed promotion on route macro F1 and answer composite gates.
- Candidate domain accuracy improved, but role macro F1 declined against the baseline, especially around memory-vs-speech, speech-vs-dream, and sparse planning/critic/dream cases.
- Answer composite remains `0.0` for both baseline and candidate, so future promotion needs a real answer-quality improvement strategy rather than threshold changes.
