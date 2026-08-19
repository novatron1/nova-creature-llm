# Nova Cognitive Operating Layer

## What changed

Nova remains the identity, memory, policy, tools, permissions, orchestration,
verification, and conversational relationship layer. Qwen remains a
replaceable semantic model behind Nova.

The existing UI, `/api/chat`, OpenAI-compatible routes, natural chat layer,
Ollama connector, raw adapter modes, checkpoints, training system, and model
weights remain in place.

## Request flow

```text
External client or existing Nova UI
  -> existing Nova HTTP/API boundary
  -> TurnState analysis
  -> selective Memory V2 retrieval
  -> local RAG retrieval when needed
  -> context budget allocation and compaction
  -> fast / deep / agent / verify routing
  -> Nova prompt construction and identity injection
  -> selected internal model provider
  -> bounded registered-tool loop when needed
  -> deterministic verification
  -> protected natural response shaping
  -> selective memory update
  -> existing response contract
```

Ordinary greetings and casual turns remain on the fast path. They do not load a
large model, run tools, or pay the cost of high-accuracy verification.

## Reasoning modes

| Mode | Typical use | Qwen3 directive | Tool steps |
|---|---|---|---:|
| `fast` | greetings, simple conversation, rewriting | `/no_think` | 0 |
| `deep` | architecture, debugging, comparisons, difficult analysis | `/think` | 0 |
| `agent` | files, project search, applications, execution | `/think` | up to 4 |
| `verify` | calculations, conflicting evidence, high-stakes facts | `/think` | only when retrieval/action is required |

Raw `<think>...</think>` content is filtered for both complete and fragmented
streaming output. It is not placed in long-term memory or safe traces.

## 8K Qwen3 model

The source model is not overwritten. Build or rebuild the alias from the
repository root:

```powershell
ollama create nova-qwen3-14b-8k -f models\nova-qwen3-14b-8k.Modelfile
ollama show nova-qwen3-14b-8k --modelfile
```

The checked model definition contains `PARAMETER num_ctx 8192`. Nova also caps
the active-brain request option to 8,192 tokens so a later connector option
cannot silently change that alias contract.

## Configuration migration

The existing `.nova_llm_config` and `nova_llm_config.json` remain the sources of
configuration. No competing YAML/config system was added. Process environment
variables now correctly take precedence over file values.

Important values:

```text
NOVA_ACTIVE_BRAIN=nova-qwen3-14b-8k
NOVA_REASONING_DEFAULT_MODE=fast
NOVA_REASONING_ALLOW_DEEP=true
NOVA_REASONING_ALLOW_AGENT=true
NOVA_REASONING_MAX_TOOL_STEPS=4
NOVA_HIDE_REASONING_CONTENT=true
NOVA_MEMORY_V2_ENABLED=true
NOVA_MEMORY_V2_DATABASE=data/nova_memory.db
NOVA_MEMORY_AUTOMATIC_WRITES=selective
NOVA_RAG_ENABLED=true
NOVA_RAG_DATABASE=data/nova_knowledge.db
NOVA_RAG_TOP_K=6
NOVA_TOOLS_ENABLED=true
NOVA_VERIFICATION_ENABLED=true
NOVA_VERIFICATION_MODE=risk_based
NOVA_MODEL_PROVIDER=existing
NOVA_TELEMETRY_ENABLED=false
NOVA_LOG_LOCAL_LLM_PROMPTS=false
NOVA_LOG_PRIVATE_MEMORY=false
```

Regular chat intentionally remains on `qwen2.5:1.5b`; the active Qwen3 brain is
selected only for deep, agent, and verification turns. This preserves the
existing small-model-first behavior.

## Conversation-intelligence controls

The July 2026 conversation upgrade uses the same two configuration files and
supports process-environment overrides:

```text
NOVA_CONVERSATION_INTELLIGENCE_ENABLED=true
NOVA_RESPONSE_REPAIR_ENABLED=true
NOVA_RESPONSE_REPAIR_MAXIMUM_ATTEMPTS=1
NOVA_CONVERSATION_SMALL_MODEL=qwen2.5:1.5b
NOVA_CONVERSATION_MIDDLE_MODEL=qwen2.5:3b
NOVA_DEEP_MODELS_REQUIRE_RESOURCE_APPROVAL=true
NOVA_CONVERSATION_CONTINUITY_ENABLED=true
NOVA_CONVERSATION_MAXIMUM_OPEN_LOOPS=8
NOVA_PERCEPTION_FUSION_ENABLED=true
NOVA_REQUIRE_CALIBRATED_DEPTH_FOR_NAVIGATION=true
NOVA_ROBOT_SIMULATION_ENABLED=true
NOVA_ROBOT_PHYSICAL_MOVEMENT_ENABLED=false
NOVA_RAW_ADAPTER_MANAGED_INTERCEPTION=false
```

Managed Nova chat now makes one shared decision for relationship, emotional,
social, follow-up, current-fact, memory, tool, vision, and reasoning turns.
The answer firewall, grounding layer, planner, and response repair consume that
same decision. Repair is deterministic and bounded to one attempt. Raw Qwen
and Raw Dolphin continue to bypass managed answer replacement, provider
fallback, and response repair.

The model tiers are:

- small: `qwen2.5:1.5b`, used first for ordinary open-ended Nova chat;
- middle: `qwen2.5:3b`, eligible when installed, healthy, and resource-safe;
- deep: larger installed local models, guarded by capability, health, memory,
  privacy, and resource-approval policy.

Missing or unhealthy tiers are skipped honestly. Nova never silently switches
to a paid or remote provider.

The chat UI shows a fixed-height, horizontally scrollable answer-status row.
Its chips report only allowlisted metadata: brain/model, intent, whether memory
or response repair was used, safety status, and vision/OCR status. `Details`
expands the same safe fields. Prompts, private memory, raw reasoning, OCR text,
and image bytes are not placed in status chips.

Conversation continuity stores a bounded factual summary, unresolved-loop
counts, active-entity labels, and broad emotional context by client and
conversation ID. It does not persist the raw prompt or full answer in the
world-model continuity record. Private mode and evaluation-only requests keep
their existing no-write behavior.

## Provider switching

The default provider value `existing` keeps the current Nova/Ollama connector.
To use a local vLLM or SGLang OpenAI-compatible server internally:

```powershell
$env:NOVA_MODEL_PROVIDER = "vllm"   # or "sglang" / "openai-compatible"
$env:NOVA_MODEL_PROVIDER_BASE_URL = "http://127.0.0.1:8000"
$env:NOVA_MODEL_PROVIDER_MODEL = "your-local-model-id"
$env:NOVA_MODEL_PROVIDER_CONTEXT = "8192"
py -3.11 nova_enhanced_server.py 8765
```

Non-loopback provider URLs are rejected unless
`NOVA_ALLOW_REMOTE_MODEL_PROVIDER=true` is explicitly set. External clients
still connect to Nova; they never connect directly to the selected provider.
Provider credentials are read only from the environment and are not returned
or logged.

## Structured Memory V2

Memory V2 uses SQLite WAL mode plus FTS5. It supports working, episodic,
semantic-user, project, procedural, reflection, and explicit memories.
Corrections supersede older records; forgetting is an auditable soft deletion;
explicit memories sort first. Ordinary conversation is saved only when it
passes selective usefulness, stability, duplication, and sensitivity checks.

The runtime database is intentionally ignored by Git:

```text
data/nova_memory.db
data/nova_memory.db-wal
data/nova_memory.db-shm
```

Explicit, semantic, project, and procedural memory persists across server
restarts and provider changes.

## RAG and reviewed AI-anatomy record

RAG ingestion stores versioned documents, sentence-aware overlapping chunks,
headings, trust/freshness metadata, FTS5 records, and optional embeddings.
Retrieval fuses lexical and vector ranks when an embedding provider exists.

Ingest the reviewed record:

```powershell
py -3.11 src\nova_rag.py ingest-ai-anatomy --database data\nova_knowledge.db
```

Search it:

```powershell
py -3.11 src\nova_rag.py search "autoregressive decoder generation" --database data\nova_knowledge.db
```

The source record is
`data/knowledge/anatomy_of_ai_field_guide_2026.json`. It includes the eight
requested corrections and labels each claim as verified technical,
conceptually simplified, author interpretation, time-sensitive, or requiring
external verification. It contains no leaked proprietary source code.

If source-dependent retrieval has no supporting passage, Nova returns an
insufficient-evidence response rather than inventing one.

## Tools and bounded agent loop

Every tool has input/output schemas, read/write class, risk, permissions,
timeout, retry policy, idempotency behavior, availability, provider, and audit
policy. Arguments are deterministically repaired once; one model regeneration
hook is supported; invalid calls then fail safely.

The new loop is finite:

```text
PLAN -> SELECT ACTION -> VALIDATE -> EXECUTE -> OBSERVE
     -> UPDATE PLAN -> VERIFY -> RESPOND
```

It defaults to four tool steps, rejects invented tools, prevents duplicate
calls, supports cancellation/timeouts, and distinguishes proposed, authorized,
attempted, observed, and verified actions. Destructive, financial, publishing,
account-changing, and external-message actions require explicit authorization.
The existing high-risk approval continuation remains active for backward
compatibility.

## Code sandbox

`nova_code_sandbox.execute_code` runs Python with:

- a disposable temporary directory;
- isolated interpreter mode;
- a minimal environment with no copied secrets;
- network and child-process audit blocking;
- host-file access blocking;
- timeout and process-tree termination;
- bounded stdout/stderr;
- a caller-controlled input-file allowlist;
- POSIX memory limits where supported;
- structured exit/output/file/policy results;
- cleanup after execution.

Windows standard-library subprocess isolation cannot enforce a kernel memory
cap; `memory_limit_supported` reports that limitation honestly. For hostile
untrusted code, use a separately configured container or VM boundary.

## Verification and final natural response

The verification layer recalculates supported math, validates JSON Schema,
checks citation IDs, verifies files, compares expected versus observed
actions, checks calendar dates, and detects duplicated/contradictory claims.
An optional model critic sees only the deterministic conclusion summary and
runs after those checks.

`nova_natural_chat.py` remains active. Its final post-verification pass may
improve warmth and flow, but reverts itself if it changes a protected citation,
date, number, code block, tool result, or explicit uncertainty statement.

## Security and release commands

Exact runtime pins:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3.11 -m nova_release_security verify-lock requirements-runtime.lock
```

Generate the SBOM:

```powershell
py -3.11 -m nova_release_security sbom reports\nova_sbom.json
```

Inspect a prepared release directory:

```powershell
py -3.11 -m nova_release_security check PATH_TO_RELEASE_DIRECTORY
```

The release check fails on source maps, environment files, private keys,
credential-like content, bytecode caches, and oversized debugging artifacts.
Telemetry, prompt logging, and private-memory logging default to off.

## Test commands

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3.11 -m pytest -q
py -3.11 tools\run_nova_cognitive_evals.py --output reports\nova_cognitive_eval_latest.json
py -3.11 tools\run_conversation_eval.py `
  --pack data\evals\nova_conversation_variations_v1.json `
  --output reports\nova_conversation_eval_v1.json
```

The conversation pack contains 560 deterministic paraphrase cases. It runs in
evaluation-only mode, writes no training records, and stores no prompt content
in the machine-readable report.

Focused safety checks:

```powershell
py -3.11 -m pytest `
  tests\test_nova_turn_analyzer.py `
  tests\test_nova_context_manager.py `
  tests\test_nova_memory_v2.py `
  tests\test_nova_rag.py `
  tests\test_nova_tool_registry.py `
  tests\test_nova_agent_loop.py `
  tests\test_nova_verifier.py `
  tests\test_nova_code_sandbox.py `
  tests\test_nova_release_security.py -q
```

## Run Nova

```powershell
py -3.11 nova_enhanced_server.py 8765
```

The existing UI remains at `http://127.0.0.1:8765/`. Nova-native health is
`/nova/v1/health`; OpenAI-compatible models are at `/v1/models`.

## Companion presentation boundary

Nova Companion is a presentation layer, not a separate brain or model route:

```text
External user
  -> Nova Companion or Nova Classic
  -> the same Nova API boundary
  -> the same cognitive core, identity, memory, tools, and model registry
```

- `/companion` opens the installable, mobile-first Companion shell.
- `/classic` always opens the existing Nova Classic interface.
- `NOVA_COMPANION_ENABLED=true` makes the Companion route available.
- `NOVA_COMPANION_DEFAULT=true` makes Companion the root `/` presentation.
  It does not change Nova's cognitive or provider routing.
- The current verified release state is
  `NOVA_COMPANION_ENABLED=true` and `NOVA_COMPANION_DEFAULT=false`, so `/`
  remains Classic while Companion is available for testing at `/companion`.
- The Companion PWA caches only the fixed public shell assets needed for
  startup and presents a truthful offline recovery page. It does not persist
  chat messages, prompts, images, audio, memory, or authentication tokens.
- A non-local client must complete Nova's pairing flow when pairing is
  required. The Trust display is a redacted projection of server-authoritative
  provider, model, privacy, cost, and action state; it never grants permission.

Both presentations call Nova's API. Companion never calls Ollama directly and
never bypasses Nova's identity, memory, tools, permissions, routing, or
verification layers.

Managed chat also has an optional Companion continuity layer. It stores bounded
relationship state in additive tables in `data/nova_memory.db`, retrieves at
most four owner-scoped memories, and passes only a compact untrusted context
projection to synthesis. Raw adapter-only, private, evaluation, and ownerless
turns bypass it. The response composer can soften social presentation, but it
does not rewrite facts, tool results, code, JSON, safety decisions, or exact
format answers. Reflective project follow-ups stay conversational unless the
user explicitly asks Nova to perform an action.

### Superpowers game check

When Nova creates a browser game, the game-builder route automatically runs
`superpowers_game_check` before returning the preview. The check verifies the
entry file, mobile viewport, render surface, WebGL/Three.js reference, Nova
runtime state API, keyboard/pointer/touch input, update/render loop, responsive
signals, obvious fatal-error markers, and placeholder content. The result is
included in the response and route trace as `SUPERPOWERS GAME CHECK` with a
score and blockers, and is saved beside the project as
`game_supercheck_report.json`. It is a bounded static safety check; the
generated game remains available for browser playtesting at its preview URL.
Raw adapter-only and private chat routes are unaffected.

The managed layer is controlled by:

```text
NOVA_COMPANION_LAYER_ENABLED=true
NOVA_COMPANION_LAYER_PERSISTENCE=true
NOVA_COMPANION_LAYER_DEBUG=false
```

For a metrics-only live check, use
`tools/run_nova_companion_live_check.py`. It exercises `/api/chat`, records
latency and safe route labels, and suppresses conversation-training writes for
the probe without changing normal chat behavior.

One-flag presentation rollback:

```powershell
$env:NOVA_COMPANION_DEFAULT = "false"
py -3.11 nova_enhanced_server.py 8765
```

For a persistent rollback, set `NOVA_COMPANION_DEFAULT=false` in
`.nova_llm_config` and `nova_llm_config.json`, then restart Nova. Keep
`NOVA_COMPANION_ENABLED=true` if `/companion` should remain available, or set
it to `false` to disable only that route. This rollback does not remove or
modify models, adapters, checkpoints, training data, identity, memory, tools,
or API behavior.

## Rollback without damaging user work

1. Stop the test/live server normally.
2. Set `NOVA_MODEL_PROVIDER=existing`,
   `NOVA_ACTIVE_BRAIN=qwen2.5:1.5b`, and disable any new layer desired with
   `NOVA_MEMORY_V2_ENABLED=false`, `NOVA_RAG_ENABLED=false`,
   `NOVA_TOOLS_ENABLED=false`, `NOVA_VERIFICATION_ENABLED=false`,
   `NOVA_CONVERSATION_INTELLIGENCE_ENABLED=false`,
   `NOVA_RESPONSE_REPAIR_ENABLED=false`,
   `NOVA_CONVERSATION_CONTINUITY_ENABLED=false`, or
   `NOVA_PERCEPTION_FUSION_ENABLED=false`.
3. Restart Nova. Existing routes, memory, natural chat, and connector continue
   to work; the new modules become dormant.
4. Keep the SQLite files as backups or copy them before removal. They do not
   alter legacy JSON memory.
5. If source rollback is required, selectively revert only the files listed in
   the upgrade audit. Do not use `git reset --hard` or a broad checkout because
   the worktree contains unrelated user-owned changes.
6. The Ollama alias is metadata over the existing model blob. It can remain
   installed without affecting regular chat.

## Known limitations

- No embedding provider is bundled. Retrieval is FTS5 lexical until a local
  embedding provider is configured.
- The web-search adapter remains unavailable until an authorized connector is
  supplied.
- vLLM and SGLang support is implemented and mocked in tests, but neither
  server was running locally for a live integration test.
- The current 16 GB CPU-only machine had about 8.5 GB free after unloading
  smaller models, while the Qwen3 14B Q4 model itself is about 9.3 GB before
  runtime/KV overhead. A real 8K generation attempt timed out after five
  minutes. The alias/configuration is valid, but this hardware cannot
  dependably run that 14B/8K path; Nova's memory guard prevents a freeze and
  the small/middle local paths remain usable.
- Moondream can be slow on this CPU and, like any vision-language model, can
  misidentify a screen. Verified local OCR takes priority for Nova Creature UI
  screenshots; other scenes retain separate semantic, OCR, and deterministic
  image observations with explicit confidence/source labels.
- Vision does not provide robot-safe metric distance by itself. Physical
  navigation remains disabled. Simulation plans require a calibrated live
  depth/LiDAR channel, obstacle/person sensing, odometry/IMU, emergency stop,
  controller feedback, and explicit movement authorization before a future
  robot backend could act.
- Windows sandbox memory caps are reported unsupported; timeout, file,
  process, environment, network, and output controls still apply.
- The release scanner was tested against clean and intentionally contaminated
  fixtures. The entire development worktree is not itself a release candidate.
