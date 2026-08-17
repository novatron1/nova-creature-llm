# Raw + Memory Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a separate `Raw + Memory` mode that supplies Nova context to the selected raw adapter while preserving the raw adapter's answer as the final response.

**Architecture:** Extend the existing allowlisted browser mode and server chat route. The server will construct a bounded context prompt for the raw adapter, call the existing raw-adapter generator, and mark the response as final raw output so quick-answer, repair, and automatic rerouting paths cannot replace it.

**Tech Stack:** Python HTTP server, existing Nova routing/memory helpers, vanilla browser JavaScript, pytest.

## Global Constraints

- Keep default and Strong modes unchanged.
- Accept only the literal browser mode `raw_memory`; never accept arbitrary model IDs.
- Preserve raw CPU/resource guards and direct raw output semantics.
- Preserve memory recall/write behavior while leaving tools/web disabled.
- Do not broad-stage pre-existing dirty worktree changes.

---

### Task 1: Server raw-memory route

**Files:**
- Modify: `nova_enhanced_server.py` near the existing raw adapter branch and managed optional-mode decision.
- Test: `tests/test_nova_enhanced_server.py` near the existing raw adapter route tests.

**Interfaces:**
- Consumes: request context fields `nova_model_mode`, `conversation_history`, `conversation_summary_history`, and the existing memory/context helpers.
- Produces: a trace with `source: "raw_memory"`, `raw_memory_mode: true`, `raw_context_turns`, selected adapter metadata, and the raw adapter result as the final response.

- [ ] **Step 1: Write the failing route test**

Add a test that patches `_generate_raw_lora_adapter`, sends `nova_model_mode: "raw_memory"` with two bounded history turns and a memory fact, and asserts the generator receives those context values, the response equals the raw output exactly, and the trace marks `raw_memory`.

- [ ] **Step 2: Run the test to verify RED**

Run: `python -m pytest tests/test_nova_enhanced_server.py -k raw_memory -q`

Expected: FAIL because `raw_memory` is not yet an accepted route.

- [ ] **Step 3: Implement the minimal route**

Add an allowlisted `raw_memory` branch before managed quick-answer recovery. Build a bounded context block from the request's conversation and memory inputs, pass it to the existing raw adapter generator, and return its `raw_output` directly. Set `trace["source"] = "raw_memory"`, `trace["raw_memory_mode"] = True`, and `trace["final_answer_source"] = "raw_memory"`. If generation returns no output, return the existing raw failure response with an explicit `fallback_reason`; do not call candidate recovery or deterministic replacement.

- [ ] **Step 4: Run the route test to verify GREEN**

Run: `python -m pytest tests/test_nova_enhanced_server.py -k raw_memory -q`

Expected: PASS.

- [ ] **Step 5: Run the focused server regression suite**

Run: `python -m pytest tests/test_nova_enhanced_server.py -k "raw_memory or raw_adapter or optional_strong" -q`

Expected: PASS with all existing raw and Strong tests green.

### Task 2: Browser mode and payload

**Files:**
- Modify: `nova_chat_web.html` in the model selector, mode state, payload builder, progress text, and message metadata rendering.
- Test: `tests/test_nova_enhanced_server.py` browser-contract tests.

**Interfaces:**
- Consumes: server mode `raw_memory` and raw-memory trace metadata.
- Produces: selector value `raw_memory`, literal payload `nova_model_mode: "raw_memory"`, and visible raw-memory status/failure text.

- [ ] **Step 1: Write the failing browser-contract test**

Assert the HTML contains a `Raw + Memory · Qwen` option, sends the literal `raw_memory` value, and renders the raw-memory route/fallback metadata.

- [ ] **Step 2: Run the test to verify RED**

Run: `python -m pytest tests/test_nova_enhanced_server.py -k "raw_memory and web_ui" -q`

Expected: FAIL because the selector and payload do not yet expose `raw_memory`.

- [ ] **Step 3: Implement the minimal browser changes**

Add the selector option and state handling without changing existing mode values. Ensure `buildChatPayload()` sends only `{nova_model_mode: "raw_memory"}` for the new managed raw-memory selection, while existing adapter-only controls remain unchanged. Add progress/status text that says the raw adapter is receiving Nova memory context and show any server-provided failure reason.

- [ ] **Step 4: Run browser-contract tests to verify GREEN**

Run: `python -m pytest tests/test_nova_enhanced_server.py -k "raw_memory and web_ui" -q`

Expected: PASS.

- [ ] **Step 5: Run the focused UI/server regression suite**

Run: `python -m pytest tests/test_nova_enhanced_server.py -k "raw_memory or optional_strong or web_ui_exposes_managed_strong or web_ui_disables_model_selector" -q`

Expected: PASS.

### Task 3: Live verification

**Files:**
- Modify: none unless a focused test exposes a regression.
- Test: local HTTP health and one raw-memory chat request.

- [ ] **Step 1: Restart the managed server through the existing watchdog**

Stop only the exact `nova_enhanced_server.py` process for port 3000 after validating its command line; allow `tools/nova_autostart.py` to relaunch it.

- [ ] **Step 2: Verify local health and served UI**

Check `GET http://127.0.0.1:3000/healthz` returns 200 and the served page contains `raw_memory` and `Raw + Memory`.

- [ ] **Step 3: Send a raw-memory smoke request**

POST `/api/chat` with `text`, `nova_model_mode: "raw_memory"`, and bounded conversation history. Confirm HTTP 200, `trace.source == "raw_memory"`, and no quick-answer replacement trace.

- [ ] **Step 4: Record the remote limitation honestly**

The Tailscale address may still return 401 until the tablet is paired; report that separately from local feature verification.
