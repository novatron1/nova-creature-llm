# Nova Companion Layer live test

Date: 2026-08-18/19 UTC

The local server was restarted from the current workspace and exercised through
the browser route, `POST /api/chat`, with the Companion layer enabled.

## Result

- Managed sequence: **8/8 passed**.
- Training dataset hash: **unchanged** during the probe.
- Reported sequence duration: **15.5 seconds**.
- Continuity follow-up route: `companion_continuity`, about **187 ms** in the final run.
- Venting route: `reviewed_conversation_response`, about **16 ms**.
- Technical-help route: `cognitive_os`, about **2.5 s**.
- Slowest observed case: joking, about **10.9 s** on the current CPU.
- Current-fact protection: `fact_grounding_guard`; Companion is intentionally not
  applied to that early protected return.

The live report contains only case IDs, latency, route labels, Companion mode,
memory counts, interaction counts, and persistence flags. It does not contain
prompts, responses, user IDs, conversation IDs, or private memory content.

## Continuity fix verified

A reflective message mentioning the ongoing project no longer enters the task
executor merely because it contains the word “project”. It now stays in the
conversation route and returns a bounded continuity answer in roughly 65 ms in
the direct smoke test. The Companion state is updated, while Raw adapter-only
requests remain outside the layer.

## Safety and deployment notes

- Raw, private, evaluation-only, and ownerless turns bypass Companion state.
- JSON, code, facts, tool results, safety decisions, and exact-format answers
  remain protected from social rewriting.
- The live checker sets a temporary no-training flag for its own requests; this
  keeps the existing training dataset unchanged while still testing the real
  managed route.
- The current CPU can still make model-backed technical or joking turns slower
  than the continuity path. The server remains responsive after each completed
  request; the checker bounds each case at 20 seconds.

Machine-readable metrics: `reports/NOVA_COMPANION_LAYER_LIVE_TEST.json`.
