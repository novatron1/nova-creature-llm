# Optional Qwen 3 8B Mode Design

## Goal

Add the already-installed `qwen3:8b` model as an optional stronger Nova mode without replacing the reliable `qwen2.5:3b` default or changing the existing raw-adapter modes.

## Selected approach

Add **Nova Strong · Qwen 3 8B** to the existing model selector. Selecting it sends a named managed mode to the server. The server maps only that allowlisted mode to `qwen3:8b` and applies it as the primary local model for model-generated replies.

Nova Strong remains inside the normal Nova route, so identity, conversation context, memory, tools, validation, and safety continue to work. Deterministic commands and reviewed direct responses may still bypass an LLM when Nova can answer more reliably without one.

The ordinary **Nova** option remains the startup and fallback default. The browser may remember the user's explicit Strong selection on that device, but server configuration is not globally rewritten.

## Alternatives considered

1. Replace the 3B model globally with 8B. This is simple, but it would make every conversation slower and increase the chance of memory pressure on this 16 GB CPU-only PC.
2. Add 8B as another raw mode. This avoids server routing changes, but it removes Nova's managed memory, tools, checks, and identity from those answers.
3. Add a managed optional mode. This preserves reliable defaults and exposes the stronger model only when the user explicitly chooses it. This is the selected approach.

## Components and data flow

1. The web selector gains a `strong` option and keeps the existing `nova`, Raw Qwen, and Raw Dolphin options.
2. Browser state tracks managed model mode separately from raw-adapter state. Choosing Strong turns both raw-adapter flags off.
3. Chat payloads include `nova_model_mode: "strong"` only while Strong is selected.
4. The server accepts only the allowlisted value `strong`, verifies the configured optional model is installed locally, and supplies the model override, timeout, keep-alive, tier, and progress label.
5. Existing Nova routing and response validation process the 8B answer normally.
6. The response trace identifies the selected managed mode and actual local model so the UI and tests can confirm what ran.

## Resource and failure behavior

- Strong mode never unloads unrelated running models automatically.
- The server uses a bounded timeout and short keep-alive appropriate for the larger model.
- If `qwen3:8b` is missing, quarantined, unavailable, or fails, Nova falls back to its normal managed route and returns a clear status instead of dropping the tablet connection.
- The UI disables model switching while a response is active and shows that Strong may be slower on CPU.
- Returning to Nova immediately restores ordinary routing for future messages.

## Configuration

Add explicit optional settings with safe defaults:

- `NOVA_OPTIONAL_STRONG_MODEL=qwen3:8b`
- `NOVA_OPTIONAL_STRONG_TIMEOUT=240`
- `NOVA_OPTIONAL_STRONG_KEEP_ALIVE=5m`

The current `NOVA_DEEP_LOCAL_LLM_MODEL=qwen2.5:3b` and `NOVA_ACTIVE_BRAIN=qwen2.5:3b` values remain unchanged.

## Testing

- HTML tests confirm the new selector option, explanatory status, and managed payload field.
- Server tests confirm only `strong` is accepted, maps to `qwen3:8b`, does not become a raw-adapter request, and takes precedence over automatic middle-model selection.
- Failure tests confirm an unavailable 8B model leaves Nova on the ordinary route.
- Existing chat, raw-adapter, routing, and mobile UI tests must continue to pass.
- A live smoke test checks the page, health endpoint, model availability, and one short Strong-mode request without changing the global default.

## Scope boundaries

This change does not replace the default model, install or remove models, alter Raw Qwen/Raw Dolphin behavior, unload another task's model, or redesign the rest of the model-management panel.
