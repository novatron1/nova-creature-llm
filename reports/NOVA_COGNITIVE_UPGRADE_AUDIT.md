# Nova Cognitive Operating-Layer Upgrade Audit

Date: 2026-07-23

## Outcome

The upgrade is integrated around Nova's existing behavior. `/api/chat`, the
natural-conversation layer, identity, legacy memory, raw Qwen/Dolphin adapters,
training protections, checkpoints, model weights, Ollama connector, and
OpenAI-compatible gateway remain in place.

No model was retrained. No checkpoint or model weight was changed. No
proprietary or leaked Claude Code implementation was used.

## Architecture discovered

```text
nova_enhanced_server.py
  /api/chat
    -> _run_nova_chat_turn
    -> brain_route
    -> src/nova_cognitive_os.py route
    -> src/nova_llm_synthesizer.py prompt/generate
    -> src/nova_local_llm_connector.py
    -> Ollama/local model
    -> src/nova_natural_chat.py
```

`src/nova_gateway` already provided Nova/OpenAI-compatible routes, provider and
model registries, permissions, authentication, structured output, health, and
optional engine boundaries. The new components extend that working foundation.

## Files created

### Runtime architecture

- `src/nova_turn_analyzer.py`
- `src/nova_context_manager.py`
- `src/nova_memory_v2.py`
- `src/nova_rag.py`
- `src/nova_model_provider.py`
- `src/nova_tool_registry.py`
- `src/nova_agent_loop.py`
- `src/nova_verifier.py`
- `src/nova_code_sandbox.py`
- `src/nova_release_security.py`

### Model, knowledge, dependency, and tooling artifacts

- `models/nova-qwen3-14b-8k.Modelfile`
- `data/knowledge/anatomy_of_ai_field_guide_2026.json`
- `requirements-runtime.lock`
- `tools/run_nova_cognitive_evals.py`

### Tests/evaluations

- `tests/test_nova_turn_analyzer.py`
- `tests/test_nova_context_manager.py`
- `tests/test_nova_memory_v2.py`
- `tests/test_nova_rag.py`
- `tests/test_nova_model_provider.py`
- `tests/test_nova_tool_registry.py`
- `tests/test_nova_agent_loop.py`
- `tests/test_nova_verifier.py`
- `tests/test_nova_code_sandbox.py`
- `tests/test_nova_release_security.py`
- `tests/evals/__init__.py`
- `tests/evals/harness.py`
- `tests/evals/test_cognitive_evals.py`

### Documentation/reports

- `docs/NOVA_COGNITIVE_OPERATING_LAYER.md`
- `reports/NOVA_COGNITIVE_UPGRADE_BASELINE.md`
- `reports/NOVA_COGNITIVE_UPGRADE_AUDIT.md`
- `reports/nova_cognitive_eval_latest.json`
- `reports/nova_sbom.json`

## Files modified

Only relevant upgrade touches are listed; the worktree contained unrelated
user-owned changes before this work.

- `.gitignore`
- `.nova_llm_config`
- `nova_llm_config.json`
- `nova_enhanced_server.py`
- `src/nova_cognitive_os.py`
- `src/nova_llm_synthesizer.py`
- `src/nova_local_llm_connector.py`
- `src/nova_natural_chat.py`
- `src/nova_gateway/core.py`
- `src/nova_gateway/tools.py`
- `tests/test_nova_llm_synthesizer.py`
- `tests/test_nova_local_llm_config.py`
- `tests/test_nova_natural_chat.py`

## New integrated request flow

```text
User input
  -> deterministic TurnState
  -> permission-aware Memory V2 retrieval
  -> RAG retrieval when required
  -> explicit 8K context budgeting/compaction
  -> fast/deep/agent/verify selection
  -> existing Nova identity and prompt construction
  -> configurable semantic provider
  -> bounded registered-tool execution when required
  -> deterministic verification
  -> protected final natural response shaping
  -> policy-controlled selective memory write
  -> existing response contract
```

The small Qwen 2.5 1.5B remains regular chat's default. Deep/agent/verify turns
select `nova-qwen3-14b-8k` when hardware policy permits. Raw adapter-only paths
remain outside Nova's answer-interception logic.

## Providers

- Existing Nova local connector: default and backward compatible
- Existing gateway Ollama provider: preserved
- Deterministic mock provider: implemented for offline tests
- Local OpenAI-compatible provider: implemented
- vLLM: supported through the local OpenAI-compatible protocol
- SGLang: supported through the local OpenAI-compatible protocol
- Remote compatible URL: rejected by default; requires explicit authorization

External applications still call Nova's API. They do not bypass Nova to call a
provider directly.

## Context and reasoning

- Separate Ollama alias created: `nova-qwen3-14b-8k`
- Verified model parameter: `num_ctx 8192`
- Fast Qwen3 turn: `/no_think`
- Deep/agent/verify Qwen3 turn: `/think`
- Complete and split streaming `<think>` traces: removed before publication
- Hidden reasoning content stored in memory: no
- Safe traces include only route decision metadata and concise outcomes

## Memory

- SQLite WAL and FTS5
- Explicit, semantic-user, project, procedural, episodic, working, reflection
- Restart persistence tested
- Correction/superseding history tested
- Forget/soft-deletion audit tested
- Exact duplicate handling tested
- Explicit memory priority tested
- `automatic_writes` policy tested
- Legacy memory preserved

## RAG

- Versioned ingestion and deduplication
- Sentence-aware chunks with headings and overlap
- FTS5 lexical retrieval
- Optional vector provider and hybrid rank fusion
- Citation-bearing passage metadata
- Missing-evidence status
- Reviewed AI-anatomy corrections ingested
- No proprietary leaked source content ingested

## Tools and agent behavior

- 16 tools reported by the live Nova health endpoint
- Typed input/output schemas
- Permission and confirmation checks
- Bounded JSON repair and one regeneration hook
- Four-step default loop; no recursion
- Duplicate tool-call prevention
- Cancellation and total timeout
- Proposed/authorized/attempted/observed/verified states
- High-risk actions held for explicit authorization
- Metadata-only audit records

## Sandbox/security

- Python isolated subprocess
- Disposable working directory
- Minimal environment
- No network by default
- Host-file access blocked by default
- Child process and shell execution blocked
- Time/output limits and process-tree termination
- Secret input-file exclusion
- POSIX memory cap where supported
- Windows memory-cap limitation reported honestly
- Release source-map, secret, key, env-file, bytecode, and debug-artifact checks
- Runtime lock verification: **passed, 2 exact pins**
- Telemetry: disabled by default
- Prompt/private-memory logging: disabled by default
- SBOM generated

## Existing and new test results

### Baseline

- 1,055 passed
- 10 skipped
- 0 failed
- 80.42 seconds

### Final full suite

- **1,112 passed**
- **10 skipped**
- **0 failed**
- **81.33 seconds**

Net result: 57 additional passing tests with a comparable full-suite runtime
(+0.91 seconds, about +1.1% on this run). Test timing is machine/load dependent.

### Cognitive evaluation suite

- 20 tasks
- 20 passed
- 0 failed
- Exact suite score: 1.0
- End-to-end suite time: 1,500 ms on the recorded run
- Machine-readable report: `reports/nova_cognitive_eval_latest.json`

The suite covers natural conversation, recall, restart persistence, correction,
deletion, RAG, citation validation, missing evidence, compaction, thinking-mode
routing, valid/repairable tools, bounded loops, duplicate prevention,
destructive authorization, sandbox isolation, calculation verification,
provider switching, think-trace filtering, and `/api/chat` contract regression.

## Live tests

A clean temporary server was tested at `127.0.0.1:8878` and stopped afterward.

- `/nova/v1/health`: healthy
- Registered tools: 16
- `/v1/models`: `nova`, `nova-coder`, `nova-deep`, `nova-default`,
  `nova-fast`, `nova-local`
- `/api/chat` greeting: fast mode, verification correctly skipped
- Post-verification natural pass: no error after live fix
- Read-only project agent request: one tool step, observed and verified
- `/v1/chat/completions`: returned an OpenAI-shaped response through Nova Core

## Model creation and hardware result

Creation command:

```powershell
ollama create nova-qwen3-14b-8k -f models\nova-qwen3-14b-8k.Modelfile
```

`ollama show` verified `num_ctx 8192`, and the alias appears in `ollama list`.

A real generation was attempted with an 8K context option and 12 output-token
limit. It timed out after about five minutes. After unloading smaller models,
the computer had about 8.52 GB free; the model blob is about 9.3 GB before
runtime/KV overhead. Therefore 14B/8K generation is not considered working on
this 16 GB CPU-only machine. Nova's model-memory policy guards against freezing;
small/middle models remain the practical local path until RAM/GPU capacity is
increased or a smaller Qwen3 quant/model is selected.

## Compatibility confirmation

- Existing `/api/chat` contract: preserved
- Existing gateway routes: preserved
- Natural conversation: active
- Nova identity: active
- Current Ollama connector: preserved
- Raw Qwen adapter mode: preserved
- Raw Dolphin adapter mode: preserved
- Training/checkpoint protections: unchanged
- Model weights: unchanged
- Raw reasoning exposed: no in tests/live fast path
- Proprietary leaked code used: no

## Known limitations

See `docs/NOVA_COGNITIVE_OPERATING_LAYER.md`. The main operational limitation is
current hardware capacity for Qwen3 14B/8K. Other boundaries are the absence of
a configured embedding provider, web connector, live vLLM server, or live
SGLang server, plus Windows' lack of a standard-library kernel memory cap for
the subprocess sandbox.

## Recommended next upgrade

Use a hardware-compatible Qwen3 reasoning model or quant as the deep provider
and run the same evaluation suite against it. The architecture is ready for
that swap; the next gain should come from a model that can complete locally
without paging, not from adding another orchestration layer.

## 2026-07-28 conversation-intelligence addendum

The follow-on upgrade added one shared managed conversation decision, bounded
natural response repair, small/middle/deep local escalation policy, portable
continuity metadata, a 560-case no-training evaluation pack, fused
OCR/vision/robot observations, and a stable privacy-safe answer-status row.

Final complete suite:

- **1,323 passed**
- **10 skipped**
- **0 failed**
- **231.21 seconds**

Final live results included 20/20 natural turns, 10/10 client-scoped
follow-ups, five honest current-fact boundaries, successful OCR/perception of
the supplied Nova phone screenshot, and HTTP 200 from all tested Nova/OpenAI
gateway surfaces. Raw adapter managed interception remains off, physical robot
movement remains off, and the evaluator wrote no training data.

The full addendum is
`reports/NOVA_CONVERSATION_INTELLIGENCE_UPGRADE.md`.
