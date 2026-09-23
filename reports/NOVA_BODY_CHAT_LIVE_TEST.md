# Body Chat Parity Live Test

Date: 2026-08-19

## Reproduction

The Body page used the legacy `/api/chat` request path while the main Chat used Nova's native `/nova/v1/chat` gateway. Body turns also were not added to the shared conversation transcript.

## Fix

Body chat now uses the native Nova gateway with the same model mode, sensor state, conversation history, summary history, request/session IDs, permissions, and response trace as the main Chat. Successful Body turns are recorded in the shared conversation context and use the same voice output.

## Live verification

- Restarted the supervised local server; `/healthz` returned `ok: true`.
- Sent `WHAT DO YOU THINK ABOUT WAR` from Body.
- Body returned the normal Nova route: `deep_conversation_router -> context_bridge -> reasoning_ladder -> speech_output`, confidence `94%`, with a measured response time.
- Sent the same prompt from main Chat; it returned the same route and answer family.
- Reloaded, sent `WHAT IS MY NAME` from Body, and confirmed the Body chat remained live and connected.
- Focused Python UI/server checks: `16 passed`.
- Full JavaScript suite: `NODE_EXIT=0`.

## Follow-up streaming and recovery check

- Body chat now uses the same streaming `/nova/v1/chat` path as the main Chat and exposes a `Talk`/`Stop` button while a Body request is active.
- The Stop path sends the native cancel request, aborts the local stream, renders `Stopped.` (without pretending it is a model answer), and restores the button/input state; the empty-input edge case is covered so Stop cannot be ignored.
- After a fresh server restart, Body answered `WHAT IS MY NAME` with `Your name is Mr Novatron. I remember you.` and then answered `WHAT DID YOU JUST ANSWER` without leaving the page stuck in Thinking.
- A longer Body prompt returned the safe fallback and restored the button to `Talk`; no duplicate request was sent.
- Final verification: `/healthz` `ok: true`, Body parity tests `2 passed`, focused UI/server checks `16 passed`, full JavaScript suite `NODE_EXIT=0`, and full enhanced-server suite `386 passed`.
