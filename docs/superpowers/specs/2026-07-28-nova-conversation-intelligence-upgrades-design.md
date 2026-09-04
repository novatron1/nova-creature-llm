# Nova Conversation Intelligence and Perception Upgrade Design

**Date:** 2026-07-28  
**Status:** Approved design  
**Scope:** Seven incremental upgrades to the existing Nova Creature runtime

## Objective

Make Nova more natural, context-aware, reliable, transparent, and useful with
vision and future robots without replacing its personality, memory, training,
checkpoints, model weights, current endpoints, natural-chat layer, provider
gateway, Ollama connector, or raw Qwen and Dolphin adapter modes.

The upgrade must eliminate repeated phrase-by-phrase repairs by giving Nova one
shared, provider-independent interpretation of each managed conversation turn.
The small Qwen 2.5 1.5B model remains normal chat's default semantic engine.
Larger local models are bounded fallbacks, not Nova's identity.

## Existing Architecture to Preserve

The active managed-chat path remains:

```text
Client
  -> /api/chat or Nova/OpenAI-compatible gateway
  -> nova_enhanced_server._run_nova_chat_turn
  -> brain_route
  -> nova_cognitive_os.route
  -> nova_llm_synthesizer
  -> nova_local_llm_connector / selected provider
  -> nova_natural_chat
  -> verification and response contract
```

The repository already contains useful foundations that this design extends:

- `nova_turn_analyzer.py`, `nova_meaning_pipeline.py`, and
  `nova_intent_planner.py` for turn classification and routing.
- `nova_answer_firewall.py`, `nova_candidate_selector.py`, and
  `nova_verifier.py` for response checking and bounded candidate selection.
- `nova_uncertainty_router.py`, `nova_model_memory.py`, gateway provider/model
  registries, and capability evaluations for replaceable model selection.
- `nova_conversation_context.py`, `nova_conversation_summary.py`, and
  `nova_gateway/world_model.py` for client-isolated continuity.
- `nova_adversarial_eval.py` and `tests/evals/` for deterministic evaluations.
- Moondream, OCR, deterministic scene analysis, browser sensor snapshots, and
  robot-navigation safety gates for vision.
- Existing response traces and mobile controls in `nova_chat_web.html`.

No parallel replacement stack will be introduced.

## Chosen Approach

Use a shared hybrid conversation core.

Deterministic normalization and intent families handle common conversational
language, slang, contractions, typos, factual boundaries, and high-risk action
markers. Existing Qwen/provider reasoning handles open-ended content. All
managed layers consume the same conversation decision instead of independently
guessing intent.

This is preferred over independent patches because independent pattern lists
have already drifted across the planner, grounding guard, cognitive route, and
answer firewall. It is preferred over model-only classification because normal
conversation must remain fast and reliable during model loading or provider
failure.

## Shared Conversation Decision

Create a provider-independent module named
`src/nova_conversation_intelligence.py`.

Its immutable `ConversationDecision` contains:

- schema and engine versions
- canonical user text hash, never the prompt text in safe traces
- intent family and subtype
- dialogue act
- subject and target
- social and emotional tone
- follow-up and context requirements
- factual-evidence requirement
- current-information requirement
- memory-read recommendation
- expected answer qualities
- preferred reasoning mode
- initial model tier
- repair policy
- confidence
- matched deterministic signals
- safe escalation reasons

The initial intent families are:

- greeting and social check-in
- Nova self-state and identity
- affection and relationship
- emotional support
- conversation follow-up
- factual and current factual
- explanation and reasoning
- coding and project work
- tool or external action
- vision and scene understanding
- robot observation and navigation planning
- memory command and memory recall
- unknown/open-ended

The module is pure policy. It calls no provider, tool, memory writer, or network
service. Managed chat computes the decision once and passes it through request
context. The turn analyzer, intent planner, fact grounding, cognitive OS,
answer firewall, response repair, and UI trace consume the same decision.

Raw adapter-only requests bypass this module exactly as they bypass existing
managed answer interception.

## Upgrade 1: Conversation Generalizer

Move shared conversational recognition into versioned intent definitions rather
than adding the same phrase to several files. Definitions support:

- canonical spelling and shorthand normalization
- contractions and omitted helper verbs
- bounded regular-expression variants
- common speech-to-text substitutions
- safe typo aliases
- exact negative examples to prevent broad matches
- expected answer qualities rather than one mandatory sentence

Existing modules keep their public interfaces. They accept an optional
`ConversationDecision`; when absent they compute one locally for backward
compatibility.

The first reviewed pack covers greetings, self-state, daily check-ins,
affection, relationship questions, emotional statements, acknowledgements,
topic continuation, requests for another item, and "why did you say that"
follow-ups.

## Upgrade 2: Natural Recovery

Create `src/nova_response_repair.py` as a bounded managed-chat repair policy.

When the answer firewall rejects a low-risk response:

1. Inspect the shared decision and firewall reason.
2. Use a reviewed deterministic repair for supported social, identity,
   relationship, memory-boundary, and capability intents.
3. Otherwise allow one existing provider-neutral candidate retry when policy
   and resources permit.
4. Re-run grounding, consistency, and firewall checks.
5. Return a natural limitation if repair still fails.

Current-fact, permission, dangerous-action, tool-result, and evidence failures
retain their strict safeguards. Technical recovery messages remain in debug
traces but normal UI copy is short and conversational. There is no recursive
retry loop and no more than one repair plus the existing bounded alternate
candidate path.

## Upgrade 3: Smart Model Escalation

Extend `nova_uncertainty_router.py`, `nova_candidate_selector.py`, and existing
resource policy instead of creating another model router.

The managed tier policy is:

1. Deterministic/reviewed response for exact safe intents.
2. Qwen 2.5 1.5B for ordinary open-ended chat.
3. Qwen 2.5 3B as the practical middle local reviewer when the first answer is
   incomplete, irrelevant, uncertain, or requires more instruction following.
4. Dolphin 8B or Qwen3 14B only for qualified deep tasks when model health and
   RAM policy permit.

Escalation combines turn difficulty, decision confidence, provider health,
required capability, firewall score, missing evidence, context size, and model
memory policy. It does not escalate greetings or supported social check-ins.
It never silently uses remote or paid providers. When a larger local model
cannot safely load, Nova repairs locally or gives a natural honest limitation.

Safe traces expose selected tier, provider/model alias, escalation reason,
resource-policy result, and fallback use. They expose no hidden reasoning.

## Upgrade 4: Conversation Continuity

Extend `nova_conversation_context.py`, `nova_conversation_summary.py`, and
`nova_gateway/world_model.py`.

Each client and conversation retains a bounded continuity ledger containing:

- active topic and recent topic transitions
- unresolved user questions
- Nova commitments and proposed next steps
- user corrections
- important stable facts already allowed by memory policy
- emotional context expressed by the user
- referenced entities and pronouns
- last successful answer type
- compact factual session digest

The ledger is isolated by client and conversation identifiers. It never merges
different users, does not persist raw private prompts in the world-model
checkpoint, and does not promote temporary conversation details into long-term
memory automatically.

Older transcript turns compact into the existing summary at the current
context threshold. Current requests, unresolved loops, explicit memories, and
active citations remain preserved.

## Upgrade 5: Conversation Evaluation Bank

Add `src/nova_conversation_eval.py` and a versioned data pack at
`data/evals/nova_conversation_variations_v1.json`.

The bank contains at least 500 deterministic cases across:

- slang and shorthand
- contractions
- speech-to-text punctuation loss
- bounded typos
- greetings and daily check-ins
- affection and relationship questions
- emotional support
- follow-up references and topic continuation
- factual versus conversational boundaries
- current-fact protection
- recovery behavior
- memory permission boundaries
- model-tier decisions
- raw-adapter bypass invariants

Each case declares expected intent family, required/prohibited route signals,
and response-quality checks. The runner produces machine-readable counts,
category scores, latency, route, model tier, repair use, and failure category.
The bank is evaluation-only and is never automatically added to training data.

## Upgrade 6: Vision and Robot Perception

Create `src/nova_perception_fusion.py` to combine existing observation sources:

- Moondream semantic description
- OCR text regions and confidence
- deterministic color, lighting, edge, and composition facts
- structured object observations parsed from the vision response
- browser sensor snapshots
- optional calibrated depth, LiDAR, IMU, and odometry observations

The fused `PerceptionSnapshot` separates observed, inferred, and unavailable
facts. It includes source, confidence, frame timestamp, coordinate convention,
staleness, and verification status.

Navigation output is a plan or simulation containing hazards, unknowns,
required sensors, suggested observation direction, and stop conditions.
Physical motor execution remains disabled. Nova must not claim metric distance,
clearance, object identity, or movement safety without the corresponding
verified observation. Existing `robot.move` permission and confirmation gates
remain unchanged.

No new vision dependency is installed in this phase. Optional object-detection
or depth engines plug into the interface later and report unavailable until
configured.

## Upgrade 7: Clearer Stable UI Status

Extend the existing mobile web UI without replacing it.

Add one compact answer-status row showing:

- Nova route/intent
- answering model tier and alias
- memory or conversation context used
- repair/escalation state
- evidence or vision engine state
- safety/verification result

The row uses fixed-height chips with concise labels. A collapsible detail panel
contains the longer explanation, resource-policy reason, source information,
and route path. It must not expose prompts, private memory content, hidden
reasoning, API keys, or authorization data.

Status updates reuse existing chat progress events. The answer list retains its
scroll position unless the user is already near the newest message. Mobile
bottom controls remain horizontally scrollable and buttons remain reachable.

## Error Handling

- Unknown conversation intents fall back to normal Qwen chat, not a fabricated
  deterministic answer.
- Low-confidence deterministic matches are advisory and cannot suppress tool,
  factual, or safety routes.
- Invalid shared decisions fail closed to existing routing behavior.
- Repair failures preserve the original safe firewall result and include a
  trace reason.
- Provider failure cannot claim model output was generated.
- Continuity corruption is quarantined per conversation and does not stop Nova.
- Evaluation-data corruption fails the evaluator and never affects live chat.
- Missing vision engines produce explicit unavailable observations.
- Stale sensor data cannot authorize navigation or movement.

## Testing and Live-Fit Gates

Every upgrade follows the same gate:

1. Add a behavior-level failing test and observe the expected failure.
2. Implement the smallest integrated change.
3. Run the focused unit and integration tests.
4. Restart the local Nova server.
5. Exercise the real endpoint or browser behavior.
6. Repair any discovered mismatch.
7. Run neighboring regression tests.
8. Continue to the next upgrade only after the gate passes.

The final audit includes:

- complete pytest suite
- 500-case conversation evaluation
- managed `/api/chat` social, factual, follow-up, recovery, and escalation tests
- raw Qwen and Dolphin bypass checks
- conversation isolation and restart continuity checks
- uploaded-picture and camera-perception checks
- robot simulation and physical-movement denial checks
- desktop and mobile UI interaction checks
- health endpoint and trace privacy checks

## Compatibility and Rollback

All new behavior is enabled through backward-compatible configuration flags.
The shared conversation decision, response repair, enhanced continuity,
perception fusion, and UI detail chips can each be disabled independently.

Rollback restores the previous managed path by disabling the new flags; no
database downgrade, checkpoint rewrite, model deletion, or training rollback is
required. Raw adapters remain independent throughout implementation and
rollback.

