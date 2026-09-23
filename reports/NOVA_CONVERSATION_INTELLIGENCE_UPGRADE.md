# Nova Conversation Intelligence Upgrade

Date: 2026-07-28

## Outcome

The seven requested upgrades are integrated and live without replacing Nova's
identity, natural chat, legacy routes, memory, Ollama connector, training
system, checkpoints, weights, or Raw Qwen/Raw Dolphin controls.

Nova now has one shared conversation decision, bounded natural recovery,
small/middle/deep local routing policy, portable continuity metadata, a
560-case no-training evaluation bank, fused OCR/vision/robot observations, and
a stable privacy-safe answer-status row.

## Final managed request flow

```text
Existing UI or compatible API client
  -> existing Nova API boundary
  -> shared ConversationDecision
  -> client-scoped recent context and continuity
  -> permission-aware memory/RAG
  -> deterministic/reviewed response when sufficient
  -> Qwen 2.5 1.5B when semantic generation is needed
  -> guarded local 3B/deep escalation when justified
  -> fact grounding, consistency, firewall, and one bounded repair
  -> natural response
  -> privacy-safe answer status
```

Raw adapter requests bypass the managed decision, repair, provider fallback,
and answer replacement paths.

## Files created for this upgrade

- `src/nova_conversation_intelligence.py`
- `src/nova_response_repair.py`
- `src/nova_conversation_eval.py`
- `src/nova_perception_fusion.py`
- `tools/generate_nova_conversation_eval_pack.py`
- `tools/run_conversation_eval.py`
- `data/evals/nova_conversation_variations_v1.json`
- `tests/test_nova_conversation_intelligence.py`
- `tests/test_nova_response_repair.py`
- `tests/test_nova_model_escalation_policy.py`
- `tests/test_nova_conversation_continuity_ledger.py`
- `tests/test_nova_conversation_eval.py`
- `tests/test_nova_perception_fusion.py`
- `tests/test_nova_answer_status_ui.py`
- `reports/nova_conversation_eval_v1.json`
- `reports/nova_conversation_eval_live_100.json`
- this report

## Files modified for this upgrade

- `.nova_llm_config`
- `nova_llm_config.json`
- `nova_enhanced_server.py`
- `nova_chat_web.html`
- `src/nova_turn_analyzer.py`
- `src/nova_intent_planner.py`
- `src/nova_fact_grounding.py`
- `src/nova_cognitive_os.py`
- `src/nova_uncertainty_router.py`
- `src/nova_local_llm_connector.py`
- `src/nova_llm_synthesizer.py`
- `src/nova_conversation_context.py`
- `src/nova_conversation_summary.py`
- `src/nova_gateway/core.py`
- `src/nova_gateway/world_model.py`
- `src/nova_tool_registry.py`
- `src/nova_adversarial_eval.py`
- `docs/NOVA_COGNITIVE_OPERATING_LAYER.md`
- `reports/NOVA_COGNITIVE_UPGRADE_AUDIT.md`
- relevant existing server, firewall, and connector tests

The worktree already contained extensive user-owned changes. This report lists
upgrade-relevant touches and does not claim ownership of unrelated dirty files.

## Models and providers

- Regular generated chat: `qwen2.5:1.5b`
- Middle local tier: `qwen2.5:3b`
- Deep tier: capability/health/resource gated local models
- Active trained adapter: `nova-qwen2-5-1-5b-balanced-calibration-20260724`
- Raw adapter controls: unchanged and managed interception disabled
- Providers exposed by Nova: `existing-nova`, `ollama`
- Aliases: `nova`, `nova-coder`, `nova-deep`, `nova-default`, `nova-fast`,
  `nova-local`

No paid or remote model was used. The live health report showed zero estimated
or actual cloud spend.

## Memory and continuity

Rolling summaries retain bounded topics, active entities, unresolved questions,
commitments, corrections, and broad emotional context. The world model stores
only safe counts/labels by client and conversation ID. It stores no prompt,
response, sensor values, or private reasoning. Schema `1.2` survived a real
server restart in the continuity audit.

Evaluation-only requests disable legacy conversation training writes, memory
writes, and summary writes. The 560-case evaluator produced the exact same
training-file SHA-256 before and after execution.

## Vision and robot boundary

The supplied 606x1280 Nova phone screenshot was live tested:

- completed in 6.414 seconds;
- correctly recognized the Nova Creature app;
- Tesseract read 946 characters across the screen;
- verified Nova-screen OCR bypassed the slower Moondream cold start;
- perception fusion recorded one OCR observation and four deterministic scene
  facts;
- image bytes, OCR content, and sensor values were not logged or persisted;
- metric depth was unavailable;
- navigation stayed `simulation_only`;
- physical movement authorization stayed `false`.

Nova can prepare a navigation plan, but a future physical robot still needs
calibrated live depth/LiDAR, obstacle/person sensing, odometry/IMU, emergency
stop, controller feedback, a registered movement tool, and explicit scope.

## UI live proof

The real in-app browser produced a natural emotional reply and these fixed
status chips:

- Brain: Nova
- Intent: emotional
- Memory: not used
- Safety: passed
- Vision: not used

The status row is fixed at 30 pixels, details are collapsible, and all chips are
created with `textContent`. At a real 390x844 mobile viewport, the answer row
and both bottom control rails scrolled horizontally without body overflow. The
activation rail moved 304 pixels in the live arrow-button test.

## Final live matrices

- Natural/slang/relationship/emotional: **20/20**, zero errors, zero bad
  fallbacks, 2.043 seconds total, 0.706 seconds slowest turn.
- Follow-up/continuity across two clients: **10/10**, all ten classified as
  follow-ups, all ten used their own client context, 2.433 seconds total,
  0.586 seconds slowest turn.
- Current-fact boundary: **5/5** returned an honest evidence/grounded route.
  The unverified example reported `current_fact` and
  `fact_grounding_blocked` in the UI status.
- Picture/OCR/perception: passed on the supplied screenshot.
- API surfaces: `/health`, `/healthz`, `/nova/v1/health`, `/v1/models`,
  `/nova/v1/providers`, `/nova/v1/capabilities`, `/nova/v1/tools`, and
  `/v1/chat/completions` all returned HTTP 200.
- OpenAI chat request: returned a valid choice through Nova Core in 3.376
  seconds.

## Tests

Baseline before this upgrade:

- 1,236 passed
- 10 skipped
- 0 failed
- 281.22 seconds

Final:

- **1,323 passed**
- **10 skipped**
- **0 failed**
- **231.21 seconds**
- **87 additional passing tests**

Conversation evaluator:

- 560 cases
- 560 passed
- 0 failed
- 0 training writes
- prompt content logged: false

Skipped tests are existing optional hardware/provider checks. No test was
deleted, weakened, or skipped to obtain the result.

## Compatibility estimates

These retain the project's existing tested estimates; they are not vendor
certification:

- OpenAI Chat Completions: **86%**
- OpenAI Responses: **60%**
- tool calling: **60%**
- structured output: **72%**
- streaming: **90%**
- MCP: **0%**

MCP client/server remain intentionally not implemented. The permission-aware
extension boundary exists, but no dependency was added or support fabricated.

## Run and connect

Local desktop:

```powershell
py -3.11 nova_enhanced_server.py 8765
```

Open `http://127.0.0.1:8765/`.

For a phone on the same Wi-Fi, first configure Nova to bind to the LAN with
API-key authentication and an appropriate Windows Firewall rule. This
computer's Wi-Fi address during the audit was `10.119.137.48`.

Compatible phone-app settings after that secure LAN setup:

```text
Provider: Custom OpenAI-compatible
Base URL: http://10.119.137.48:8765/v1
API key: the configured Nova client key
Model: nova
API format: Chat Completions
```

`localhost` and `127.0.0.1` work only on the Nova computer. LAN addresses can
change after reconnecting to Wi-Fi, so recheck with:

```powershell
Get-NetIPAddress -AddressFamily IPv4
```

## Rollback

Stop Nova, set any desired switch in the process environment or existing
`.nova_llm_config`, then restart:

```text
NOVA_CONVERSATION_INTELLIGENCE_ENABLED=false
NOVA_RESPONSE_REPAIR_ENABLED=false
NOVA_CONVERSATION_CONTINUITY_ENABLED=false
NOVA_PERCEPTION_FUSION_ENABLED=false
```

Keep `NOVA_RAW_ADAPTER_MANAGED_INTERCEPTION=false` and
`NOVA_ROBOT_PHYSICAL_MOVEMENT_ENABLED=false`. Source rollback should be
file-selective; do not use a destructive broad reset in this dirty worktree.

## Known limitations

- CPU semantic generation can still be slow. Reviewed social and follow-up
  paths now avoid unnecessary model loads, but truly open-ended questions still
  use Qwen.
- Qwen3 14B/8K does not fit dependably in the current 16 GB CPU-only machine.
- Moondream remains partial for non-screen scene semantics and can be slow;
  OCR is authoritative only for verified Nova UI screenshots.
- ComfyUI is configured but was not reachable in the final health check, so
  image/video generation is currently unavailable until that local service is
  started.
- Physical robot movement is not implemented or authorized.
- Anthropic compatibility and MCP are not implemented.

## Recommended next upgrade

Add a local embedding/reranking provider and evaluate a hardware-compatible
4B-class reasoning model as Nova's deep tier. That would improve open-ended
knowledge retrieval and reasoning without weakening the fast deterministic
conversation paths or loading a 14B model this machine cannot sustain.
