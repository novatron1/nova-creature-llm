# Validated Conversation Cascade Design

## Goal

Make Nova's normal conversation route preserve only trustworthy context, retry weak answers through an available local model tier, and prevent firewall recovery text from becoming future conversation memory.

## Evidence and constraints

The live route audit reproduced three related failures: a routine statement could end in `answer_firewall_recovery`, a subsequent follow-up reused that recovery text as the prior answer, and the configured middle/deep reviewer could be unavailable because of capability or memory gates. The repair must preserve action, raw-adapter, private-mode, and current-fact safety gates.

Recent routing research supports a guarded cascade rather than a single learned router: coarse routing is often competitive with more complex routers, model recall remains a major failure mode, and cascade quality depends on an explicit quality estimator. Nova already has deterministic intent, uncertainty, answer-firewall, and candidate-selector layers, so the smallest safe change is to connect those layers through a validated conversation-state packet.

## Design

### 1. Validated conversation state

`src/nova_conversation_context.py` will define the boundary for context eligibility. Bounded history and focus selection will ignore known provider/recovery outputs, while retaining user turns so an unanswered request can be recognized as pending. The resolver will expose a safe `last_valid_exchange` and never treat a recovery sentence as Nova's answer.

### 2. Guarded cascade

Normal managed chat continues to use deterministic policy gates first. If the primary answer fails the answer firewall or is an unqualified fallback, the existing candidate selector may try the next eligible local tier. If no tier is available, the route returns one contextual fallback derived from the current request and valid prior exchange. The fallback is marked as a recovery event and is not committed as a valid assistant turn.

### 3. State commit policy

The managed turn wrapper snapshots legacy conversation state before routing. It commits `_LAST_USER_TEXT` and `_LAST_NOVA_RESPONSE` only when the final trace identifies a validated answer. Recovery/fact-blocked/provider-error responses leave the previous valid exchange intact and record a privacy-safe pending-turn marker in the trace. Client-supplied history is filtered by the same eligibility predicate.

### 4. Evaluation

Add regression tests for recovery filtering, valid-state commit, non-recursive follow-ups, and candidate escalation metadata. Run the focused suites, the broader conversation/server suites, and a live six-turn route pack. Compare baseline and repaired metrics for route family, fallback recurrence, valid-context continuity, and latency. Persist only sanitized counts and labels.

## Non-goals

- No learned router training in this patch.
- No changes to raw adapter output, memory writes, tool permissions, or safety policy.
- No raw public conversation dataset or user prompt text in reports.
