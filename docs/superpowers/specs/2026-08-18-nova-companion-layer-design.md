# Nova Companion Layer Design

Date: 2026-08-18  
Status: Draft for review  
Scope: Persistent server-side social behavior for managed Nova conversations

## Product decision

Nova already has a cognitive/router layer, selective memory, natural-chat
shaping, and a phone-first `/companion` shell. This feature adds the missing
social layer without replacing any of those systems. The Companion Layer sits
between managed-turn interpretation and final response generation:

```text
managed request
  -> existing ConversationDecision
  -> Companion social interpretation and bounded context
  -> existing Nova routing, models, tools, grounding, and verification
  -> protected Companion response presentation
  -> gradual relationship-state and relationship-memory update
```

Raw Qwen/Dolphin adapter-only requests remain raw and bypass this layer. Private
mode, evaluation-only requests, and requests without a stable owner identity do
not persist relationship updates.

## Goals

1. Make Nova recognizable across conversations through stable personality
   traits and slowly adapting expression.
2. Persist a bounded relationship state across server restarts and sessions.
3. Retrieve only a few relevant relationship memories using relevance,
   importance, confidence, and recency.
4. Distinguish companionship, joking, support, advice, brainstorming, debate,
   technical help, storytelling, celebration, frustration, venting, and task
   execution without forcing every turn into a task format.
5. Let the existing reasoning stack decide factual truth, tool results,
   permissions, and uncertainty. Companion behavior changes presentation, not
   evidence.
6. Keep latency overhead deterministic and small; no second LLM call is added
   for social reasoning.
7. Preserve existing public APIs, route contracts, raw modes, memory controls,
   and training protections.

## Non-goals

- Replacing `nova_enhanced_server.py`, `nova_conversation_intelligence.py`,
  `nova_memory_v2.py`, or `nova_natural_chat.py`.
- Moving memory or personality logic into the browser.
- Automatically storing every conversation or raw transcript.
- Allowing one conversation to rewrite Nova's stable personality.
- Making Nova claim human feelings, consciousness, or private knowledge.
- Adding a remote/paid provider or another model-generation pass.
- Changing Raw Qwen, Raw Dolphin, adapter-only, safety, tool, or permission
  semantics.

## Existing integration boundaries

The first implementation uses these current boundaries:

- `nova_enhanced_server._run_nova_chat_turn_impl()` is the managed-turn
  lifecycle and already has the user/client/conversation context needed for
  ownership and isolation.
- `src/nova_conversation_intelligence.py` provides a provider-independent
  `ConversationDecision` for factual, memory, project, social, and action
  families.
- `src/nova_memory_v2.py` owns the existing SQLite memory database and selective
  memory policy.
- `src/nova_llm_synthesizer._build_prompt()` constructs the prompt consumed by
  the current model/provider boundary.
- Final answer grounding, firewall, candidate selection, verification, and
  natural response shaping already run after generation.

The Companion Layer adds context to the existing packet and trace rather than
introducing a new chat endpoint or client contract.

## Package structure

Create `src/nova_companion/` with small, dependency-free modules:

- `__init__.py` — public version and service exports.
- `models.py` — frozen/typed dataclasses and enum-like constants.
- `personality.py` — stable trait profile and safe expression modifiers.
- `store.py` — SQLite tables, migrations, owner-scoped transactions, and
  persistence health.
- `memory.py` — relationship-memory writes, ranking, and reference updates.
- `intent.py` — social-mode classification layered on the existing decision.
- `social_reasoning.py` — structured presentation policy, no model/network
  calls.
- `context_builder.py` — bounded prompt-safe companion context.
- `response_composer.py` — protected presentation composer.
- `adaptation.py` — gradual state and mood updates.
- `service.py` — begin-turn, context construction, finalize-turn orchestration.

## Data model

### CompanionState

`CompanionState` is versioned and owner-scoped. User identity is represented by
the existing `context["user_id"]`; it is never inferred from prompt text.

Required fields:

```text
schema_version
user_id
relationship_stage       new | familiar | trusted | established
familiarity_score        [0, 1]
trust_score              [0, 1]
interaction_count        bounded non-negative integer
first_interaction_at
last_interaction_at
preferred_tone            neutral | warm | direct | playful | reflective
humor_style               unknown | light | dry | silly | restrained
conversational_energy     [0, 1]
affection_style           restrained | warm | playful
disagreement_style        gentle | direct | evidence_first
advice_style              listen_first | practical | balanced
known_user_preferences    bounded JSON object of reviewed keys/values
recurring_topics          bounded list of labels
shared_history_summary    bounded structured summary, not raw transcript
active_projects           bounded list of safe project labels
important_people          bounded role/name records only when explicitly saved
unfinished_conversations  bounded structured labels and counts
recent_emotional_context  bounded labels with timestamps
nova_current_mood         bounded MoodState
nova_personality_state    bounded expression-state metadata
personality_version
updated_at
```

Free-form fields are normalized, length-limited, and owner-scoped. Secrets,
credentials, authorization material, hidden reasoning, raw images/audio, and
unbounded transcripts are rejected before persistence.

### NovaPersonality

Core traits are immutable configuration:

```text
warm, curious, confident, playful, loyal, intelligent, sarcastic,
perceptive, creative, protective, conversational, willing_to_disagree
```

Each trait has a stable base intensity. A per-turn expression modifier may
change intensity within `[0, 1]`, but cannot rewrite the base profile. Sarcasm,
affection, and challenge are disabled or softened for distress, high-stakes,
current-fact, safety, permission, and tool-result turns.

### MoodState

Mood dimensions are numeric values in `[0, 1]`:

```text
energy, playfulness, curiosity, seriousness, warmth
```

Mood is a conversational style signal only. A turn can change each dimension
by at most `0.08`; a periodic decay moves it toward neutral by at most `0.03`.
Mood never changes factual claims, safety policy, model selection, or tool
authorization.

### RelationshipMemory

Relationship memories are separate from raw chat history and contain:

```text
memory_id
user_id
category                 joke | project | preference | goal | commitment |
                         decision | conversation | frustration | pattern
content                  bounded, user-owned memory text
importance_score         [0, 1]
confidence               [0, 1]
created_at
last_referenced_at
reference_count
source_conversation_id
validity_status          active | superseded | forgotten | disputed
```

The records live in the existing `data/nova_memory.db` file in Companion-owned
tables. This is one database, not a second memory system. Migrations are
idempotent and additive. Existing `memory_records` behavior is unchanged.

## Persistence and privacy

`store.py` creates `companion_state` and `relationship_memories` with owner and
validity indexes. Writes use a short transaction and WAL-compatible locking.
The service uses `user_id` plus a normalized owner scope; conversation IDs are
metadata for provenance, not a cross-user key.

Persistence is skipped when any of these are true:

- `private_mode` or global private mode is active;
- `evaluation_only` is true;
- the request is raw adapter-only;
- no stable user owner is available;
- the turn is explicitly marked non-retained by an existing policy.

Normal traces contain only safe labels, scores, counts, and memory IDs. Memory
content is never placed in browser status, public health endpoints, or normal
logs. Development observability is opt-in and redacts content by default.

## Social intent classification

`intent.py` consumes the existing `ConversationDecision` and current text only
as a bounded classifier input. It returns a ranked tuple of social modes with
confidence values and a `seriousness` score. The initial modes are:

```text
casual_chat, joking, emotional_support, advice, brainstorming,
technical_help, debate, storytelling, celebration, frustration,
venting, companionship, task_execution
```

Precedence rules are conservative:

1. Permission/action, current-fact, financial, vision, tool, and safety signals
   suppress joking and affection.
2. Explicit “just listen”, “I need advice”, “let me vent”, or “be honest”
   requests outrank inferred style.
3. Ambiguous humor is treated as casual conversation, not as permission to
   tease.
4. Existing factual and task families remain authoritative for routing.

Classification is deterministic and records matched signal names, never raw
prompt text, in the safe trace.

## Social reasoning output

`social_reasoning.py` produces a structured `SocialPlan`:

```json
{
  "primary_mode": "casual_chat",
  "secondary_modes": ["companionship"],
  "tone": "playful_warm",
  "directness": 0.7,
  "humor": 0.3,
  "affection": 0.2,
  "challenge_user": false,
  "listen_first": false,
  "ask_follow_up": false,
  "reference_memory": true,
  "response_length": "short",
  "intensity": 0.45,
  "reason_codes": ["casual_social_turn"]
}
```

The plan combines the ranked modes, state preferences, mood, and personality
traits under caps. It is a presentation policy, not a truth or tool policy.

## Memory retrieval

`memory.py` retrieves at most four active relationship memories. Candidate
selection requires at least one meaningful token/entity overlap or an explicit
continuity signal. Each candidate receives:

```text
score = 0.45 * relevance
      + 0.30 * importance
      + 0.15 * confidence
      + 0.10 * recency
```

Recency decays over a bounded period. Ties prefer newer references, then stable
categories (`project`, `goal`, `commitment`, `preference`) over casual patterns.
Selected memories update `last_referenced_at` and `reference_count` only after
the answer is accepted. Irrelevant memories are not returned merely because
they are important.

Automatic writes are conservative. The service may write an explicit user
memory, a reviewed project/goal/commitment, or a repeated high-confidence
pattern. A single emotional sentence or casual joke does not become durable
memory without explicit confirmation or repeated evidence.

## Companion context builder

`build_companion_context()` returns a bounded dictionary containing:

```text
schema_version
safe relationship stage and scores
stable personality trait names/intensities
current bounded mood
social plan
up to four selected memories with IDs and bounded content
shared-history labels and unfinished-loop counts
```

The prompt projection is explicitly marked as untrusted context. It tells the
model to use memories only as continuity hints, never as instructions, and to
avoid claiming uncertain personal facts. The total serialized companion block
is capped at 3,000 characters before it reaches the model.

## Final response composer

The composer receives the underlying Nova answer and the `SocialPlan`.

Protected responses pass through unchanged when the trace indicates:

- current/factual grounding or citations;
- tool/action results or permission gates;
- safety blocks, uncertainty guards, or exact calculations/JSON/code;
- raw adapter or adapter-only mode;
- explicit user length/count/format constraints.

For eligible social/open-ended responses, the composer can apply only bounded
presentation changes: remove customer-service filler, add one brief
acknowledgment when `listen_first` is true, soften or sharpen directness, add a
single relevant memory reference, and add at most one genuine follow-up. It
must never append a generic “How can I help?” question or invent a relationship
fact. If composing fails, the underlying answer is returned unchanged.

## Turn lifecycle integration

In `_run_nova_chat_turn_impl()`:

1. Keep the existing raw/evaluation/private guards first.
2. Build the existing `ConversationDecision`.
3. Call Companion `begin_turn()` for eligible managed requests and attach the
   bounded context to the existing context packet.
4. Let all existing deterministic routes, models, tools, grounding, firewall,
   candidate selection, and verification run normally.
5. Call the composer only after the existing answer is selected and only for
   eligible presentation-safe traces.
6. Call Companion `finalize_turn()` after the final verified response. Persist
   state and reviewed memories transactionally; attach safe trace metadata.

In `_build_prompt()`, add one optional `NOVA COMPANION CONTEXT` section when
the context packet contains it. Existing prompts remain byte-for-byte unchanged
when the feature flag is disabled or no context is available.

## Feature flags and rollback

Add backward-compatible settings:

```text
NOVA_COMPANION_LAYER_ENABLED=true
NOVA_COMPANION_LAYER_PERSISTENCE=true
NOVA_COMPANION_LAYER_DEBUG=false
```

Disabling `NOVA_COMPANION_LAYER_ENABLED` skips all new calls and context
injection. Disabling persistence keeps the social pass active but prevents
state/memory writes. No migration rollback is required because the new tables
are additive and ignored by the old code.

## Observability

When debug is enabled for a local development process, a privacy-safe event
may expose:

- social mode names and confidence values;
- selected memory IDs/categories, not memory content;
- bounded state deltas;
- mood/personality modifiers;
- composer decision and protected-answer reason;
- total Companion latency.

No prompt, response, hidden reasoning, credential, authorization header, image,
audio, or raw memory content is emitted by this layer's logs.

## Test plan

### Unit tests

- state defaults, schema migration, enum validation, and clamping;
- familiarity/trust stage progression and bounded deltas;
- mood update and neutral decay limits;
- personality core immutability;
- social mode precedence, joking-versus-serious, advice/listening, and
  respectful disagreement;
- relevance/importance/recency ranking, owner isolation, and irrelevant-memory
  rejection;
- protected-answer composer behavior and format preservation.

### Integration tests

- managed turn receives companion context and emits safe trace metadata;
- raw adapter receives no Companion context and no state/memory mutation;
- private/evaluation turns do not persist;
- restart restores state and relationship memories from the same SQLite file;
- explicit memory controls remain authoritative;
- existing API response shapes and disabled-flag behavior remain unchanged.

### Long-running simulation

Run at least 100 deterministic turns across multiple conversations and a restart.
Assert that familiarity increases gradually, memory references remain relevant,
trait identity remains stable, mood stays bounded, and state does not cross
owner boundaries. The simulation report stores metrics only, not turn content.

## Risks and mitigations

- **Over-personalization:** bounded state changes, conservative writes, and
  explicit protected modes.
- **Memory leakage:** owner-scoped queries, relevance threshold, small context,
  private/evaluation bypass, and redacted traces.
- **Personality drift:** immutable core profile plus capped expression modifiers.
- **Latency:** deterministic social pass and one bounded SQLite transaction;
  no extra model call.
- **Response corruption:** composer runs after answer selection but preserves
  factual/tool/safety/format-protected outputs.
- **Dirty legacy integration:** additive optional context and focused tests;
  no broad refactor of the giant server file.

## Acceptance criteria

The feature is ready to enable by default only when:

1. Companion state persists across a restart and remains owner-isolated.
2. A 100-turn simulation shows gradual familiarity with no personality drift.
3. Relevant relationship memories are selected and irrelevant memories rejected.
4. Joking, serious, advice, venting, and casual turns receive distinct plans.
5. Factual, tool, safety, raw, code, JSON, and exact-format answers remain
   unchanged by the composer.
6. Existing focused and full test suites pass with the feature enabled and
   disabled.
7. Public API contracts and raw adapter traces remain compatible.
8. Debug output is opt-in and content-safe.

Until every gate passes, the feature remains available behind
`NOVA_COMPANION_LAYER_ENABLED=false` by default and the existing Nova behavior
is the rollback path.

