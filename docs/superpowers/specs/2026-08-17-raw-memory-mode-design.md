# Raw + Memory Mode Design

## Goal

Add a distinct chat mode that gives the raw selected adapter Nova's recent conversation and approved memory context, then displays the adapter's response directly without quick-answer substitution or managed answer rewriting.

## Behavior

- The model selector adds `Raw + Memory · Qwen` as an explicit option.
- The mode follows the selected raw adapter: Qwen by default, Dolphin when explicitly selected.
- The browser sends the allowlisted mode `raw_memory`; it never sends arbitrary model identifiers.
- The server builds the same bounded conversation and memory context used for Nova, then wraps that context into the raw-adapter prompt.
- The raw adapter output remains the final answer. Deterministic quick answers, candidate retries, answer repair, and automatic middle/deep routing must not replace it.
- Memory recall and approved memory writes remain enabled around the raw turn; tools, web access, and live-fact verification remain disabled.
- If the adapter cannot run, return a visible, structured failure/fallback reason; do not silently answer through the quick route.
- Existing Nova, Nova Strong, Raw Qwen, and Raw Dolphin modes keep their current behavior.

## Data flow

`browser selector → nova_model_mode: raw_memory → managed raw-memory route → bounded memory/context prompt → raw adapter → direct response + trace`

The trace identifies `raw_memory`, the adapter used, the context turn count, and any adapter failure reason. It must not claim that a raw adapter generated the answer when the call did not occur.

## Safety and compatibility

- Keep the current adapter allowlist and raw CPU safety guards.
- Keep raw-adapter answer-firewall bypass semantics; the raw output is not rewritten into a managed answer.
- Keep the existing Strong mode and default `qwen2.5:3b` configuration unchanged.
- Keep selector locking while any chat request is in flight.

## Verification

- Server tests prove the raw-memory route receives bounded conversation/memory context and returns the raw output unchanged.
- Server tests prove quick-answer/recovery replacement is not invoked for raw-memory mode.
- Browser tests prove the selector and literal payload value.
- Focused server and UI regression suites must pass.
