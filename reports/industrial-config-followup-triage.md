# Full-suite follow-up: six failures

Only tests/test_nova_local_llm_config.py and tests/test_nova_foundation.py changed in this follow-up. No runtime or operator configuration changes.

- Foundation UI contract was stale: the existing Steps input defaults to 24, with its 1-200 validation range unchanged. Updated the exact markup assertion from 8 to 24.
- Code-default routing threshold and strong-model tests read operator config before checking defaults. A temporary ROOT fixture now exercises the actual config loader against test files. Known config environment keys are cleared; both runtime-log and conversation-training suppression guards are explicitly true. Existing file precedence and exact override assertions remain active, rather than mocking away the loader.
- The options override test keeps its exact 8192 code-default context assertion and exact temperature/token overrides; the fixture removes the unrelated shipped 4096 override.
- Shipped JSON tests separately reflect the intentional configuration: regular/fast/active brain remains Qwen 2.5 1.5B, deep/strong/reviewer is Qwen 3 4B, LoRA is CUDA, context is 4096, escalation timeout is 45, base/strong timeout is 240. Added relational assertions that active brain matches fast model and strong differs from fast, preserving the actual invariant instead of claiming optional strong cannot also serve the deep route. Existing tool permissions, disabled shell/file/web actions, direct Dolphin route, and other safety checks remain exact.
- Removing operator config exposed four generation tests which relied on its NOVA_USE_LOCAL_LLM=true. Each now explicitly enables that option within its fake-provider scenario; production defaults remain unchanged.
- Added a regression proving fixture-active write guards are true and real temporary JSON loading still works.

Validation: python -m pytest tests/test_nova_local_llm_config.py tests/test_nova_foundation.py -q --tb=short -p no:cacheprovider --junitxml=reports/industrial-config-followup.xml

Result: **39 passed in 8.84s**. Whitespace diff checks passed. No broad suite was started by this subtask.
