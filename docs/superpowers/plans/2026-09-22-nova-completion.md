# Nova Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the currently working Nova desktop app into a release candidate whose promised chat, memory, tools, media, remote access, recovery, packaging, and release evidence are verified on Windows.

**Architecture:** Keep the existing local-first server and browser UI. Complete the work in vertical slices: first fix and lock down the shared chat response contract, then verify each UI subsystem through its real API boundary, then close release and packaging evidence. Preserve the current feature boundaries and report unsupported integrations explicitly.

**Tech Stack:** Python 3.12, pytest, Node test runner, vanilla HTML/JavaScript, SQLite, Ollama/local gateway, Playwright, PowerShell, Windows Sandbox where available.

**Spec:** `docs/NOVA_INDUSTRIAL_GATE.md`, `reports/app-repair-readiness-20260906.md`, and the completion findings recorded in the user request.

## Global Constraints

- Nova remains local-first and must not expose Ollama port 11434.
- Remote phone access remains private Tailscale Serve plus Nova pairing.
- Release bundles exclude secrets, live configuration, memories, logs, training data, and model weights.
- Raw Qwen and Raw Dolphin modes remain explicit modes and bypass managed answer replacement.
- Existing user-owned dirty changes must be preserved and classified before release.
- Unsupported MCP and ComfyUI extension boundaries must either be implemented or documented as unavailable.
- Every release claim requires fresh test evidence from the exact candidate being shipped.

## Review Focus

- Exact-output requests such as “only the number” must preserve the requested format; owned by the chat response contract tests.
- Cold model startup and API timeouts must produce a bounded, truthful error; owned by gateway/live-chat tests.
- Stop, retry, duplicate submission, and restart during generation must leave no stuck composer or duplicate turn; owned by browser and server integration tests.
- User, device, and conversation memory must not cross scopes; owned by identity and memory restart tests.
- Sandbox and packaging failures must leave no locked files and no promotable false positive; owned by industrial gate and release tests.

### Task 1: Exact-output chat contract

**Files:**
- Modify: `src/nova_response_repair.py`, `src/nova_llm_synthesizer.py`, and the shared answer path identified by the regression.
- Test: existing chat/conversation tests plus a focused regression in `tests/test_nova_live_chat_regressions.py`.

- [x] Write a failing test for a managed request that asks for only a number and assert the final answer is exactly `42`.
- [x] Run the focused test and capture the current extra wording failure.
- [x] Trace where answer status, repair, or managed synthesis adds prose after a valid constrained answer.
- [x] Implement the smallest contract-preserving repair that honors explicit output constraints without changing normal conversational responses.
- [x] Run the focused regression and the existing response-repair, synthesizer, and browser chat tests.

### Task 2: Live chat resilience

**Files:**
- Modify: `nova_enhanced_server.py`, `src/nova_gateway/http.py`, and the live chat path only if evidence identifies a defect.
- Test: `tests/test_nova_enhanced_server.py`, `tests/test_nova_gateway_http.py`, `tests/test_nova_live_chat_regressions.py`, and a fresh browser probe report.

- [ ] Add or reuse a bounded cold-start test for `/api/chat` and native `/nova/v1/chat`.
- [ ] Reproduce timeout, connection loss, Stop, retry, and duplicate-submit behavior with diagnostic evidence at UI, HTTP, and model boundaries.
- [ ] Implement one root-cause fix per reproduced defect, including truthful progress/error state.
- [ ] Run the focused tests, 20-chat browser probe, and a fresh restart sequence.

### Task 3: Feature acceptance matrix

**Files:**
- Modify: only feature modules that fail acceptance.
- Test: the existing subsystem test files plus real-browser/API acceptance reports under `reports/runtime-refresh/`.

- [ ] Exercise Chat, Home, Display, Dream Studio, Agent Library, App Builder, GPU Hub, Memory, Tools, Research, Test/Check, Projects, Preview, Logs, Scheduler, Files, and Settings.
- [ ] For each feature record success, failure, unavailable dependency, latency, and recovery behavior.
- [ ] Fix only reproducible defects and add a regression beside the owning subsystem.
- [ ] Mark unsupported MCP and ComfyUI features explicitly in UI and docs unless implementation is required by scope.

### Task 4: Memory, privacy, and recovery

**Files:**
- Modify: `src/nova_identity_memory.py`, `src/nova_runtime/`, recovery modules, and UI only where tests identify a defect.
- Test: identity, memory, runtime permissions, ledger, recovery, backup, and restart tests.

- [ ] Verify user/device/conversation isolation with separate owners and processes.
- [ ] Verify save, recall, correction, delete, private mode, export, backup, restore, corrupt storage, interrupted write, and full-disk handling.
- [ ] Verify background jobs recover without duplicate execution after restart.
- [ ] Add missing regressions and run the isolated and integration suites.

### Task 5: Remote phone and media acceptance

**Files:**
- Modify: remote launcher, pairing routes, media job handlers, and mobile-facing UI only when acceptance exposes a defect.
- Test: pairing, revocation, Tailscale status, media engine, download, resume, cancel, and phone browser evidence.

- [ ] Verify private remote link, pairing expiry, revocation, reconnect, touch layout, and host-sleep behavior.
- [ ] Verify image/video generation, unavailable explicit engines, cancellation, download integrity, and restart recovery.
- [ ] Record GPU and CPU capability boundaries in the release documentation.

### Task 6: Release candidate and industrial gate

**Files:**
- Modify: `tools/run_nova_industrial_gate.py`, Sandbox proof, release lock, packaging scripts, and docs only for verified defects or stale claims.
- Test: full industrial gate, Sandbox/symlink proof, release rollback, standalone build, clean-machine smoke test.

- [ ] Classify current dirty files as source, generated evidence, runtime state, model assets, or user data.
- [x] Run the integrated gate on a fresh candidate and verify the unit, filesystem-symlink, and audit cleanup phases. The final candidate passes all required phases; only repository cleanliness blocks promotion.
- [x] Build `dist/nova-standalone-20260922`, inspect its manifest, and verify it excludes forbidden data.
- [ ] Test install, launch, health, chat, shutdown, upgrade, rollback, and uninstall on a clean Windows environment.
- [ ] Repeat the full gate against the exact final candidate and require promotion allowed before calling the app release-ready.

### Task 7: Documentation and handoff

**Files:**
- Modify: `README_LAPTOP_INSTALL.md`, `docs/NOVA_STANDALONE_INSTALL.md`, `docs/NOVA_GATEWAY_CONNECTION_GUIDE.md`, and a final readiness report.

- [ ] Replace broad unverified capability claims with measured, tested behavior.
- [ ] Document supported hardware, model, network, and recovery limits.
- [ ] Record exact candidate identity, commands, test totals, skipped checks, known limitations, and release artifacts.
- [ ] Link the local and private remote launch instructions and troubleshooting paths.
