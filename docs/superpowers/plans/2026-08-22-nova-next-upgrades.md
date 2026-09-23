# Nova Next Upgrades Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Nova dependable in normal conversation, transparent about routing and latency, easier to manage over time, reliable for CPU/GPU media generation, and installable as a standalone Windows application.

**Architecture:** Preserve Nova as the identity, memory, permission, and tool owner. Keep model providers and media engines replaceable behind existing gateway interfaces. Deliver four independently testable phases: conversation reliability, conversation/archive controls, media/GPU reliability, and standalone packaging.

**Tech Stack:** Python standard-library gateway, existing Nova cognitive pipeline, Ollama/ComfyUI adapters, browser UI assets, FFmpeg, PowerShell installer scripts, pytest, Node browser-contract tests.

**Spec:** `docs/NOVA_GATEWAY_ARCHITECTURE.md` and `docs/NOVA_RELEASE_LOCK.md`.

## Global Constraints

- Normal conversation uses an LLM by default; deterministic routes are limited to information placement, exact calculations, memory operations, tools, and safety-critical handling.
- Generic fallback text is allowed only after every eligible LLM/provider path fails.
- Raw adapter modes remain explicit and are never intercepted, rewritten, or quality-scored by managed routing.
- Prompt text, answer text, private reasoning, secrets, and model weights are not written to operational telemetry or job ledgers.
- Media output must report the actual engine and render mode; CPU fallback must not be labeled as true temporal diffusion.
- Existing `/api/chat`, `/v1/*`, `/nova/v1/*`, pairing, memory, training, and release-lock behavior must remain compatible.
- Every task ends with focused tests and a diff check before moving to the next task.

---

## Phase 1 — Conversation reliability and truthfulness

### Task 1: Build a conversation regression corpus and route contract

**Files:**
- Create: `tests/fixtures/nova_conversation_regression.json`
- Create: `tests/test_nova_conversation_regression.py`
- Modify: `src/nova_gateway/router.py`
- Modify: `src/nova_llm_synthesizer.py`

**Interfaces:**
- Consumes: provider-neutral Nova requests and current route traces.
- Produces: a bounded, repeatable route-quality contract covering greetings, follow-ups, emotional conversation, factual questions, coding, memory recall, tools, and media requests.

- [x] Write failing cases for LLM-first normal conversation, substantive follow-ups, and “generic fallback only after all providers fail.”
- [x] Run the focused tests and record the expected failures.
- [x] Implement the smallest routing/fallback changes while preserving deterministic routes.
- [x] Run the focused regression suite and verify route traces contain no prompt or answer text.

### Task 2: Add truthful route, model, backend, and timing metadata

**Files:**
- Modify: `src/nova_protocol.py`
- Modify: `src/nova_gateway/http.py`
- Modify: `nova_chat_web.html`
- Modify: `nova_companion_web.html`
- Test: `tests/test_nova_gateway_http.py`
- Test: `tests/js/test_nova_chat_ui.js`

**Interfaces:**
- Consumes: completed provider response metadata and media job engine metadata.
- Produces: stable UI-safe fields for route name, model, backend, latency, fallback reason, and completion state.

- [x] Add failing API/UI assertions for elapsed milliseconds and truthful engine labels.
- [x] Implement bounded metadata propagation and a compact “Details” view.
- [x] Verify raw, managed, deterministic, CPU, and GPU paths each report distinct correct labels.

### Task 3: Add the 100-case live-style conversation gate

**Files:**
- Create: `tools/nova_conversation_gate.py`
- Create: `reports/nova_conversation_gate.md`
- Modify: `docs/NOVA_RELEASE_LOCK.md`

- [x] Add a deterministic mock-provider mode for repeatable route checks.
- [x] Run 100 cases across normal, raw, memory, tool, and failure scenarios.
- [x] Fail the gate on wrong route class, generic fallback before provider exhaustion, missing timing, or leaked private text.
- [x] Record the baseline and post-fix report.

---

## Phase 2 — Chat archive and memory controls

### Task 4: Add conversation archive/search/save/delete API

**Files:**
- Create: `src/nova_gateway/conversations.py`
- Modify: `src/nova_gateway/core.py`
- Modify: `src/nova_gateway/http.py`
- Create: `tests/test_nova_conversations.py`

**Interfaces:**
- Consumes: authenticated client ID, conversation ID, bounded transcript metadata.
- Produces: list, search, save/rename, export, archive, restore, and delete operations with ownership checks.

- [x] Write failing ownership, deletion, restore, and export tests.
- [x] Implement an atomic, versioned metadata store that excludes private reasoning and secrets.
- [x] Verify concurrent writes and malformed records do not break startup.

### Task 5: Add archive and memory controls to the desktop/mobile UI

**Files:**
- Modify: `nova_chat_web.html`
- Modify: `nova_mobile_app.html`
- Modify: `assets/nova_dream_studio.js`
- Test: `tests/js/test_nova_chat_archive_ui.js`

- [x] Add failing browser-contract tests for search, save, delete, export, and confirmation dialogs.
- [x] Implement responsive archive controls and explicit destructive-action confirmation.
- [x] Verify the current chat remains stable while the archive panel opens on phone and desktop widths.

---

## Phase 3 — Media quality, GPU switching, and resumable jobs

### Task 6: Make media engine selection explicit and truthful

**Files:**
- Modify: `src/nova_gateway/core.py`
- Modify: `src/nova_gateway/http.py`
- Modify: `src/nova_gateway/animatediff_cpu.py`
- Modify: `src/nova_gateway/video_lite.py`
- Test: `tests/test_nova_media_selection.py`

- [x] Write failing tests for requested CPU, local GPU, remote GPU, Video Lite, and true AnimateDiff selection.
- [x] Add an explicit engine selector with safe fallback only when the requested backend is unavailable.
- [x] Add a quality gate that rejects empty, tiny, corrupted, or visibly invalid outputs and reports the fallback mode.
- [x] Verify the generated cat clip reports the actual render mode.

### Task 7: Add resumable media jobs and download integrity

**Files:**
- Modify: `src/nova_gateway/video_lite.py`
- Modify: `src/nova_gateway/animatediff_cpu.py`
- Modify: `src/nova_gateway/http.py`
- Test: `tests/test_nova_media_jobs.py`

- [x] Write failing tests for restart recovery, cancellation, byte ranges, checksum, and expired output handling.
- [x] Implement atomic job checkpoints and HTTP range responses for completed MP4 files.
- [x] Verify a stopped job can resume without duplicating paid work or losing ownership metadata.

### Task 8: Finish GPU Hub switching and diagnostics

**Files:**
- Modify: `src/nova_gpu_hub.py`
- Modify: `src/nova_gateway/model_registry.py`
- Modify: `nova_chat_web.html`
- Modify: `nova_enhanced_server.py`
- Test: `tests/test_nova_gpu_hub.py`
- Test: `tests/test_nova_gpu_hub_http_contract.py`

- [x] Add failing tests for local GPU scan, CPU-only mode, remote worker verification, lease expiry, and provider mismatch.
- [x] Implement one visible effective-backend state shared by chat, media, and diagnostics.
- [x] Verify switching off GPU never silently routes to a stale remote worker.

---

## Phase 4 — Standalone Windows packaging and repair

### Task 9: Add first-run diagnostics and repair mode

**Files:**
- Create: `tools/nova_doctor.py`
- Modify: `INSTALL_NOVA_GPU_HUB_WINDOWS.ps1`
- Modify: `NOVA_GPU_HUB_INSTALL.bat`
- Create: `tests/test_nova_doctor.py`

- [x] Write failing checks for Python, Ollama, ComfyUI, FFmpeg, ports, model paths, writable directories, and remote-GPU connectivity.
- [x] Implement a non-destructive doctor report plus targeted repair actions.
- [x] Verify repair never deletes models, memories, checkpoints, or user data.

### Task 10: Produce a portable standalone release candidate

**Files:**
- Modify: `tools/nova_release_lock.py`
- Modify: `config/nova_release_snapshot_policy.json`
- Create: `tools/build_nova_windows_release.ps1`
- Modify: `ANDROID_INSTALL_GUIDE.md`
- Create: `docs/NOVA_STANDALONE_INSTALL.md`

- [x] Add failing release checks for missing launcher, config template, doctor, health endpoint, and rollback metadata.
- [x] Build a release candidate without including secrets, checkpoints, adapters, memories, logs, or model weights.
- [x] Run install, launch, health, local chat, media smoke test, and uninstall/rollback checks.

---

## Final verification

- [x] Run all focused Python and Node suites for the four phases.
- [x] Run the release-lock candidate gates and inspect the manifest.
- [x] Run `py_compile` on changed Python files and `git diff --check`.
- [x] Run the live local health, chat, archive, GPU status, and media output checks.
- [x] Document known limits, especially CPU diffusion quality and model download requirements.
- [x] Do not claim release-ready until the one known enhanced-server fixture failure is either fixed or explicitly waived.
