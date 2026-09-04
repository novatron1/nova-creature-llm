# LLM-First Normal Chat Design

**Goal:** Keep ordinary conversation on the configured LLM while reserving deterministic routes for information retrieval, device state, permissions, and actions.

## Behavior

- Normal conversational prompts use the LLM as the answer producer.
- Deterministic routes remain authoritative for memory operations, live/current facts, GPU/device status, permissions, and tool/action execution.
- The router prepares a bounded context packet for the LLM containing the user message, recent turns, detected subject/intent, retrieved memory, and successful tool results. It must not expose internal route-planning prose as the answer.
- If the primary LLM fails or produces an unsafe/unusable answer, Nova retries the configured fallback LLM before any canned response.
- Existing safety, privacy, and action-approval gates remain unchanged.

## Scope

The implementation is limited to the normal managed chat path and its tests. Raw adapter mode, explicit tool/action routes, memory stores, and GPU controls keep their existing ownership and contracts.

## Acceptance criteria

1. Ordinary conversational prompts reach the LLM answer path and do not return planner/recovery text such as “I caught that” or “inner routing”.
2. Contextual follow-ups preserve their subject through the LLM context packet.
3. Information/action prompts still use their deterministic routes and retain trace metadata.
4. A failed primary LLM attempts the fallback LLM before generic recovery.
5. Local and remote `/api/chat` smoke tests pass, and routing regressions are covered by automated tests.
