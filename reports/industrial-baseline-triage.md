# Industrial baseline failure triage

Baseline: 21 failed, 427 passed (448 tests), reports/industrial-baseline.xml.

## Confirmed runtime defects (four baseline failures)

- `test_brain_route_researches_flat_earth_debate_before_cognitive_os` and `test_brain_route_live_research_fetches_source_pages`: source/evidence list helpers mistakenly started with conversational instructions and a blank line. Limiting the list to two entries removed actual citation URLs and made an empty source list appear nonempty. Removed those unrelated entries; added a regression checking empty lists, successful citations, fetched evidence, and failed-source exclusion.
- `test_automatic_model_quality_check_honors_runtime_config_when_env_is_unset`: automatic-check enablement ignored JSON/dotenv settings. It now reads runtime settings with process environment taking precedence. Existing regression failed before the fix and passes after.
- `test_run_chat_blocks_inconsistent_larger_local_candidate`: consistency guard rejected the technical candidate correctly, but a social-plan misclassification let the companion replace the truthful failure with a generic social answer, set accepted=true, and commit the turn. Composer protection now runs before social fallback and preserves rejected consistency/evidence and failed verification. Added two failing-then-passing composer regressions. The integration test uses a real temporary companion database and verifies rejection remains visible and conversation state is not committed.

## Live configuration contamination (eleven baseline failures)

- Synthesizer prompt/timeout and direct-middle override tests (2): operator timeout 240 overrode test assumptions (120 default and 175 explicit minimum).
- Routing status and installed middle-model selection (2): operator model/threshold differed from the test's installed-model scenario.
- Optional strong installed/malformed/quarantine cases (3): tests supplied Qwen 3 8B while operator configuration selected another model, so validation never reached the intended condition.
- Middle quarantined/full-qualification cases (2): operator preferences excluded the supplied test model before the intended checks.
- Registered local provider protocol request (1): operator escalation timeout 45 differed from the code-default 180 scenario.
- New safe flags/default routing (1): operator middle model Qwen 3 4B differed from the code-default Qwen 2.5 3B scenario.

Both unit modules now isolate NOVA environment settings and skip machine config-file loading. After clearing settings, both fixtures explicitly reassert NOVA_SUPPRESS_RUNTIME_LOGS=true and NOVA_SUPPRESS_CONVERSATION_TRAINING=true, so isolation retains the supervisor write guards. A regression in each module asserts those flags while its fixture is active (both failed before this fix and passed after). Server feature projections use an empty settings fixture unless a test explicitly overrides it. These assertions test deterministic code defaults; they do not change or claim to describe the operator's deployed configuration. No operator configuration files were edited.

Isolation also exposed a further runtime defect: when fast and active models are the same, synthesis increased an explicitly brief prompt's 4096 context to 8192. The active-model cap now respects the already-selected smaller prompt budget. Existing one-idea regression reproduced the failure before this fix.

## Stale expectations or mixed scenarios (six baseline failures)

- Raw Qwen CPU flag (1): backend deliberately allows slow CPU generation for explicit raw selection. Assertion now reflects that documented policy. The UI separately sends `allow_slow_dolphin_cpu=false`; neither production policy was changed.
- Raw memory explicit recall (1): the test's adapter returned an unrelated sentence for a name query and read live long-term memory, despite the current guarded-memory contract. It now isolates saved-memory reads and returns the supported name from the injected recall result, still verifying that result reaches the raw prompt and final answer.
- UI context, Dolphin flag, Strong selector, and managed mode literal (4): updated assertions for 20-message role/content projection, GPU-oriented UI flag, Qwen 3 4B/GPU text, and the added Dolphin Deep managed mode. Other marker assertions remain intact.

## Isolation and validation boundaries

Generic server routing units disable the companion service boundary to avoid reading or writing the live relationship database. The personality-to-cognitive-model regression and firewall/companion integration explicitly inject real services backed by temporary databases. The personality assertion `intelligent == 0.86` remains intact and passes.

Unit model/provider scenarios use fakes; HTTP handler tests use their local temporary loopback servers. This is unit/integration evidence, not a live-model quality, latency, deployment, or restart claim. Existing unrelated dirty changes, including the personality patch, were preserved. No commits or restart were performed.

Final command:

`python -m pytest tests/test_nova_enhanced_server.py tests/test_nova_llm_synthesizer.py tests/test_nova_companion_composer.py -q --tb=short -p no:cacheprovider --junitxml=reports/industrial-repaired.xml`

Final result is recorded in reports/industrial-repaired.txt and reports/industrial-repaired.xml.

Final verified result: **458 passed in 43.53 seconds; zero failures** (451 server/synthesizer tests plus 7 composer tests).
