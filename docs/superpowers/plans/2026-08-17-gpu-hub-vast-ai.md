# Nova GPU Hub and Vast.ai Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone, installable GPU Hub that lets Nova use CPU, a detected local GPU, or a user-approved Vast.ai GPU and reports the active choice truthfully on desktop and phone.

**Architecture:** A focused `nova_gpu_hub` module owns compute-mode state, local GPU discovery, and the Vast.ai REST client. Nova's existing server exposes small `/api/gpu-hub/*` routes and the existing provider layer remains responsible for inference. The HTML panel is a separate top-level surface and never receives credentials; a worker bootstrap plus Windows check/installer makes the remote path reproducible.

**Tech Stack:** Python 3.10+ standard library (`urllib`, `subprocess`, `json`, `pathlib`), existing `http.server` Nova server, vanilla HTML/CSS/JS, pytest, Node's built-in test runner, PowerShell/batch shell scripts.

## Global Constraints

- Compute modes are exactly `auto`, `cpu`, `local_gpu`, and `vast_gpu`.
- Auto may fall back to CPU; the other modes must report unavailability instead of silently changing mode.
- Vast API keys are read from `NOVA_VAST_API_KEY` only, never returned to the browser or written to runtime state.
- Paid Vast start/create/destroy operations require an explicit confirmation field and are never triggered by health checks.
- No public Ollama/vLLM exposure or arbitrary shell/desktop control is added.
- All network calls have bounded timeouts and redact credentials from errors/logs.
- Existing chat/provider/raw-memory behavior remains unchanged when the hub is disabled or unused.
- Runtime state is ignored, atomically written, and safe to reset.

---

### Task 1: Core GPU Hub state, local scan, and Vast client

**Files:**
- Create: `src/nova_gpu_hub.py`
- Create: `tests/test_nova_gpu_hub.py`
- Modify: `.gitignore`

**Interfaces:**
- `ComputeMode` constants: `AUTO`, `CPU`, `LOCAL_GPU`, `VAST_GPU`.
- `detect_local_gpu(*, runner=None) -> dict[str, object]` returns `available`, `usable`, `gpu_names`, `memory_mb`, `driver`, `backend`, and `reason`.
- `GpuHubStateStore(path).load() -> dict` and `.save(state) -> dict` persist only mode, selected instance id, endpoint metadata, and timestamps.
- `VastAIClient(api_key, base_url="https://console.vast.ai/api/v0", timeout=15)` exposes `list_instances()`, `show_instance(instance_id)`, `search_offers(filters)`, `create_instance(offer_id, payload, *, confirmed=False)`, `set_instance_state(instance_id, state, *, confirmed=False)`, and `destroy_instance(instance_id, *, confirmed=False)`.
- `GpuHubController(root, env=None)` exposes `status()`, `set_mode(mode)`, `local_status()`, `vast_status()`, `vast_instances()`, `vast_search(filters)`, `vast_create(...)`, `vast_set_state(...)`, and `vast_destroy(...)`.

- [ ] **Step 1: Write failing core tests**

  Add tests for valid/invalid mode transitions, missing state recovery, atomic state redaction, mocked `nvidia-smi` parsing, no-GPU CPU truthfulness, Vast URL/auth/header construction, response normalization, and confirmation-required start/destroy behavior. Assert that API-key text never appears in any returned value.

- [ ] **Step 2: Run the focused tests and verify RED**

  Run: `py -3.11 -m pytest tests/test_nova_gpu_hub.py -q`

  Expected: import/function failures because the module does not yet exist.

- [ ] **Step 3: Implement the minimal core module**

  Use a single `urllib.request.Request` helper with a 15-second cap, `Authorization: Bearer ...`, JSON parsing, structured `GpuHubError(code, message, status)`, and a redaction function. Parse `nvidia-smi` CSV without importing torch; optionally report a discovered `torch.cuda` backend only when it is already importable. Use a temp file plus `os.replace` for state writes and default invalid/missing state to `auto`.

- [ ] **Step 4: Run the focused tests and verify GREEN**

  Run: `py -3.11 -m pytest tests/test_nova_gpu_hub.py -q`

  Expected: all core tests pass and no key-like value is present in serialized status.

- [ ] **Step 5: Add ignored runtime state and commit**

  Add `data/nova_gpu_hub_state.json` to `.gitignore`, then run:

  ```powershell
  git add -- src/nova_gpu_hub.py tests/test_nova_gpu_hub.py .gitignore
  git commit -m "feat: add GPU Hub core and Vast client"
  ```

---

### Task 2: Nova HTTP routes and provider-selection bridge

**Files:**
- Create: `tests/test_nova_gpu_hub_http_contract.py`
- Modify: `nova_enhanced_server.py`
- Modify: `src/nova_model_provider.py`

**Interfaces:**
- `GET /api/gpu-hub/status` returns `{ok, enabled, mode, effective_backend, local, vast, selected_instance, endpoint}` with secrets removed.
- `POST /api/gpu-hub/mode` accepts `{mode}`.
- `POST /api/gpu-hub/vast/test` validates the configured key without mutating state.
- `GET /api/gpu-hub/vast/instances` lists instances.
- `POST /api/gpu-hub/vast/search` searches offers without renting.
- `POST /api/gpu-hub/vast/create` accepts `{offer_id, payload, confirmed:true}`.
- `POST /api/gpu-hub/vast/state` accepts `{instance_id, state, confirmed:true}`.
- `POST /api/gpu-hub/vast/destroy` accepts `{instance_id, confirmed:true}`.
- `POST /api/gpu-hub/remote-model/test` accepts `{endpoint, model, api_key?}` but never stores the supplied key; it performs only `/v1/models` or `/health` validation.
- `build_gpu_hub_provider_settings(state) -> dict` produces provider settings for the existing OpenAI-compatible provider and leaves ordinary provider settings untouched when mode is `cpu` or `auto` without a verified GPU.

- [ ] **Step 1: Write route-contract tests**

  Use a lightweight fake handler/controller boundary rather than starting the whole server. Assert every route, mode rejection, confirmation rejection, key redaction, and provider bridge behavior.

- [ ] **Step 2: Run route tests and verify RED**

  Run: `py -3.11 -m pytest tests/test_nova_gpu_hub_http_contract.py -q`

  Expected: route symbols and bridge are missing.

- [ ] **Step 3: Implement server integration**

  Import one controller at server startup, add GET/POST dispatch before the 404 branches, map `GpuHubError` to safe status codes, and keep the provider bridge opt-in. Add a `NOVA_GPU_HUB_ENABLED` flag defaulting to true for local status and false for remote lifecycle actions unless a Vast key is configured.

- [ ] **Step 4: Run route tests and compatibility checks**

  Run:

  ```powershell
  py -3.11 -m pytest tests/test_nova_gpu_hub_http_contract.py tests/test_nova_gpu_hub.py -q
  py -3.11 -m pytest tests/test_nova_enhanced_server.py -q
  ```

  Expected: focused tests and the existing enhanced-server suite pass.

- [ ] **Step 5: Commit**

  ```powershell
  git add -- nova_enhanced_server.py src/nova_model_provider.py tests/test_nova_gpu_hub_http_contract.py
  git commit -m "feat: expose GPU Hub routes and remote provider bridge"
  ```

---

### Task 3: Standalone responsive GPU Hub UI

**Files:**
- Create: `tests/js/test_nova_gpu_hub_ui.js`
- Modify: `nova_chat_web.html`

**Interfaces:**
- New top-level tab `GPU Hub` opens `gpu-hub-panel`.
- UI elements use stable ids: `gpuHubMode`, `gpuHubLocalState`, `gpuHubVastState`, `gpuHubInstances`, `gpuHubEndpoint`, `gpuHubMessage`.
- Browser functions: `loadGpuHubStatus()`, `setGpuHubMode(mode)`, `scanGpuHubLocal()`, `testGpuHubVast()`, `loadGpuHubInstances()`, `setGpuHubVastState(...)`, and `destroyGpuHubInstance(...)`.

- [ ] **Step 1: Write failing browser-contract tests**

  Assert the tab, panel, four mode options, explicit confirmation text, no API-key input persisted in localStorage, and calls to the route names above.

- [ ] **Step 2: Run the UI contract and verify RED**

  Run: `node --test tests/js/test_nova_gpu_hub_ui.js`

  Expected: missing marker/function failures.

- [ ] **Step 3: Add the responsive panel and client code**

  Add one horizontally safe panel that works at phone width, loads status when opened, disables lifecycle buttons while requests are in flight, renders redacted errors, and requires `window.confirm` for start/stop/destroy. Keep Vast keys out of HTML, localStorage, and DOM values.

- [ ] **Step 4: Run UI contracts and a served-page smoke test**

  Run: `node --test tests/js/test_nova_gpu_hub_ui.js tests/js/test_nova_raw_memory_ui.js`; fetch the served HTML and assert the GPU Hub markers are present.

- [ ] **Step 5: Commit**

  ```powershell
  git add -- nova_chat_web.html tests/js/test_nova_gpu_hub_ui.js
  git commit -m "feat: add standalone GPU Hub panel"
  ```

---

### Task 4: Standalone Vast worker bootstrap, Windows installer/check, and docs

**Files:**
- Create: `tools/nova_vast_worker_bootstrap.sh`
- Create: `INSTALL_NOVA_GPU_HUB_WINDOWS.ps1`
- Create: `NOVA_GPU_HUB_INSTALL.bat`
- Create: `tests/test_nova_gpu_hub_install_assets.py`
- Modify: `QUICK_START_LAPTOP.txt`
- Modify: `README_LAPTOP_INSTALL.md`

**Interfaces:**
- Bootstrap accepts `NOVA_WORKER_MODEL`, `NOVA_WORKER_PORT`, and `NOVA_WORKER_ENGINE` (`vllm`, `sglang`, or `ollama`) and starts only the selected OpenAI-compatible worker.
- PowerShell installer checks Python, creates `data`, runs the core smoke check, and prints the safe `NOVA_VAST_API_KEY` setup instruction without collecting or echoing the key.
- Batch launcher invokes the PowerShell installer and leaves existing server startup unchanged.

- [ ] **Step 1: Write asset tests**

  Assert scripts exist, use strict error behavior, do not contain a literal API key, expose the engine/model/port variables, and point to the GPU Hub panel and health endpoint.

- [ ] **Step 2: Run asset tests and verify RED**

  Run: `py -3.11 -m pytest tests/test_nova_gpu_hub_install_assets.py -q`

  Expected: missing asset failures.

- [ ] **Step 3: Implement scripts and documentation**

  The bootstrap must fail closed when model/engine is missing, bind the worker to the instance interface required by the configured tunnel, and print the internal port. The Windows installer must not modify existing model files or write credentials.

- [ ] **Step 4: Run asset tests and installer dry-run**

  Run:

  ```powershell
  py -3.11 -m pytest tests/test_nova_gpu_hub_install_assets.py -q
  powershell -NoProfile -ExecutionPolicy Bypass -File .\INSTALL_NOVA_GPU_HUB_WINDOWS.ps1 -CheckOnly
  ```

  Expected: all checks pass and no server/model state changes occur.

- [ ] **Step 5: Commit**

  ```powershell
  git add -- tools/nova_vast_worker_bootstrap.sh INSTALL_NOVA_GPU_HUB_WINDOWS.ps1 NOVA_GPU_HUB_INSTALL.bat tests/test_nova_gpu_hub_install_assets.py QUICK_START_LAPTOP.txt README_LAPTOP_INSTALL.md
  git commit -m "feat: add GPU Hub installer and Vast worker bootstrap"
  ```

---

### Task 5: Live verification and release handoff

**Files:**
- Create: `reports/gpu_hub_live_test_latest.json`
- Modify: `.superpowers/sdd/2026-08-17-gpu-hub-vast-ai/progress.md`

- [ ] **Step 1: Run the complete focused suite**

  Run the four new test files plus the existing gateway/provider/UI regression suites. Record exact pass counts.

- [ ] **Step 2: Start Nova and verify local endpoints**

  Start the existing Windows server, check `/healthz`, `/api/gpu-hub/status`, CPU-only mode, and local scan. Verify that chat still returns in CPU mode.

- [ ] **Step 3: Verify Vast behavior without spending**

  With no key, confirm `test` returns a clear `vast_key_missing` result and no secret. With `NOVA_VAST_API_KEY` present, call only list/show/status and remote-model health. Do not create or destroy an instance unless the user explicitly supplied an instance id and confirmed the charge-bearing action.

- [ ] **Step 4: Run installer dry-run and served mobile smoke**

  Run the PowerShell check-only path, fetch the served HTML, verify the GPU Hub panel markers, and confirm the panel opens at a narrow viewport through the existing browser smoke tooling.

- [ ] **Step 5: Write evidence and hand off**

  Store redacted results in the report and progress ledger. State clearly whether a real Vast instance/model was live-tested or whether the live check stopped at missing credentials/no paid instance. Do not claim GPU inference passed unless the remote model health and a bounded test response both succeed.

