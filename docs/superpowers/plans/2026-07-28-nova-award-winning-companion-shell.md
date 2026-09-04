# Nova Award-Winning Companion Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a phone-first Living Cosmos companion interface that makes Nova feel alive and understanding while preserving the existing Nova cognitive system and Nova Classic interface.

**Architecture:** Add a standards-based HTML/CSS/ES-module shell at `/companion` that calls Nova's existing HTTP APIs through a small typed browser service. Keep `/classic` and the current root behavior available behind two runtime flags until every release gate passes; no browser module owns identity, memory, routing, model, tool, or permission truth.

**Tech Stack:** Python 3.11, existing `BaseHTTPRequestHandler` server, HTML5, CSS, browser ES modules, Node.js built-in test runner for DOM-free JavaScript, pytest, existing Nova Gateway SSE and Foundation pairing APIs.

## Global Constraints

- Preserve `nova_enhanced_server.py`, `/api/chat`, `/nova/v1/chat`, Nova identity, natural conversation, memory, cognitive routing, models, adapters, checkpoints, training protections, tools, and permissions.
- Keep Nova Classic directly accessible throughout development and after release.
- Add no frontend framework, package manager, bundler, CDN, font download, or runtime dependency.
- Use existing Foundation device pairing and `authHeaders()` rather than creating a second token system.
- Do not store conversation messages, private memory, images, audio, API keys, or hidden reasoning in browser persistence or service-worker caches.
- Raw Qwen and Raw Dolphin controls remain unintercepted and available through Nova Classic.
- Companion is enabled but is not the default until all acceptance gates pass.
- Primary phone test viewports are exactly `390x844` and `430x932` CSS pixels; desktop coverage begins at `1024` CSS pixels.
- Primary touch targets are at least `44x44` CSS pixels.
- Support `prefers-reduced-motion: reduce`, visible keyboard focus, semantic controls, focus restoration, and a WCAG AA contrast baseline.
- Target a warm local-network interactive shell time below `1.5` seconds, excluding model generation.
- Preserve the design-time regression baseline of `1,323 passed`, `10 skipped`, `0 failed`; never delete, weaken, or skip an existing test to make Companion pass.
- The existing worktree contains user-owned changes. Never reset, clean, stash, or bulk-stage it. Every commit command in this plan stages only the files named for that task.
- At execution start, record `git status --short`. Before every commit, compare that record with `git diff` and `git diff --cached`. If a tracked file was already dirty, stage only the task-owned hunks with `git add -p -- <path>` and inspect the staged diff; if task ownership cannot be proven, leave that file unstaged and report the deferred commit instead of absorbing existing work.

---

## File Structure

### New application files

- `nova_companion_web.html` — semantic Companion document and stable mount points only.
- `assets/nova_companion/companion-shell.css` — Living Cosmos tokens, safe-area layout, responsive rules, accessibility, and component styles.
- `assets/nova_companion/companion-app.js` — application lifecycle and module coordination.
- `assets/nova_companion/companion-store.js` — deterministic presentation-state reducer.
- `assets/nova_companion/companion-api.js` — authenticated fetch, SSE parsing, cancellation, health, and normalized errors.
- `assets/nova_companion/companion-presence.js` — Evolved Nova view model and truthful presence rendering.
- `assets/nova_companion/companion-conversation.js` — message and artifact DOM rendering without `innerHTML`.
- `assets/nova_companion/companion-composer.js` — text input, draft recovery, submit/stop, and mobile keyboard behavior.
- `assets/nova_companion/companion-spark.js` — accessible capability registry, menu, sheets, and Classic deep links.
- `assets/nova_companion/companion-senses.js` — explicit camera, picture, OCR/vision, microphone, and TTS presentation.
- `assets/nova_companion/companion-trust.js` — pairing, local/remote state, memory use, permissions, and safe recent activity.

### New tests and audit files

- `tests/test_nova_companion_routes.py` — Companion/Classic routes, feature flags, headers, and static assets.
- `tests/test_nova_companion_source.py` — semantic markup, security invariants, accessibility hooks, and forbidden persistence.
- `tests/test_nova_companion_javascript.py` — launches Node's built-in test runner.
- `tests/js/companion-store.test.mjs` — reducer and presence-state tests.
- `tests/js/companion-api.test.mjs` — SSE, cancellation, pairing error, and duplicate-delta tests.
- `tests/js/companion-spark.test.mjs` — capability filtering and safe route mapping.
- `tests/js/companion-senses.test.mjs` — deterministic image metadata and voice-state tests.
- `tests/js/companion-trust.test.mjs` — safe trust projection and redaction tests.
- `tests/test_nova_companion_pwa.py` — manifest and service-worker cache boundaries.
- `tools/run_nova_companion_acceptance.py` — repeatable no-training HTTP acceptance report.
- `reports/NOVA_COMPANION_RELEASE_AUDIT.md` — measured results and known limitations.

### Existing files modified

- `nova_enhanced_server.py` — load Companion HTML, add `/companion` and `/classic`, project Companion configuration, and select the root experience.
- `src/nova_foundation_http.py` — serve the new static asset allowlist.
- `assets/nova_foundation_ui.js` — expose the existing validated pairing-token helpers and expand the safe Classic panel allowlist.
- `.nova_llm_config` — add Companion enable/default flags.
- `nova_llm_config.json` — add the same backward-compatible flags.
- `manifest.webmanifest` — make Companion installable and retain a Classic shortcut.
- `service-worker.js` — cache only shell assets and exclude API/content responses.
- `offline.html` — add Companion-specific reconnect and Classic fallback links.
- `docs/NOVA_COGNITIVE_OPERATING_LAYER.md` — document the presentation boundary and rollback.

---

### Task 1: Add the Companion HTTP Boundary and Rollback Flags

**Files:**
- Create: `nova_companion_web.html`
- Create: `tests/test_nova_companion_routes.py`
- Modify: `nova_enhanced_server.py:246-338`
- Modify: `nova_enhanced_server.py:13201-13208`
- Modify: `nova_enhanced_server.py:13564-13594`
- Modify: `src/nova_foundation_http.py:78-115`
- Modify: `.nova_llm_config`
- Modify: `nova_llm_config.json`

**Interfaces:**
- Consumes: existing `_runtime_config_values()`, `NovaHandler._send_cors_headers()`, `WEB_HTML`, and `FoundationHttpController.UI_ASSETS`.
- Produces: `_companion_ui_config() -> dict[str, bool]`, `COMPANION_WEB_HTML: str`, `GET /companion`, `GET /classic`, and a flag-controlled `GET /`.

- [ ] **Step 1: Write failing route and configuration tests**

```python
def test_companion_config_defaults_to_enabled_but_not_default(monkeypatch):
    monkeypatch.delenv("NOVA_COMPANION_ENABLED", raising=False)
    monkeypatch.delenv("NOVA_COMPANION_DEFAULT", raising=False)
    monkeypatch.setattr(server, "_runtime_config_values", lambda: {})
    assert server._companion_ui_config() == {"enabled": True, "default": False}


def test_companion_classic_and_default_routes(monkeypatch):
    monkeypatch.setattr(server, "_companion_ui_config", lambda: {"enabled": True, "default": False})
    httpd, base_url = start_server()
    try:
        assert get_text(base_url, "/classic") == server.WEB_HTML
        assert get_text(base_url, "/companion") == server.COMPANION_WEB_HTML
        assert get_text(base_url, "/") == server.WEB_HTML
        monkeypatch.setattr(server, "_companion_ui_config", lambda: {"enabled": True, "default": True})
        assert get_text(base_url, "/") == server.COMPANION_WEB_HTML
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_disabled_companion_route_is_not_found(monkeypatch):
    monkeypatch.setattr(server, "_companion_ui_config", lambda: {"enabled": False, "default": False})
    httpd, base_url = start_server()
    try:
        assert get_status(base_url, "/companion") == 404
        assert get_status(base_url, "/classic") == 200
    finally:
        httpd.shutdown()
        httpd.server_close()
```

Use the same `ThreadingMixIn + HTTPServer` helper pattern as
`tests/test_nova_gateway_http.py:29-37`. `get_text()` must assert
`Content-Type: text/html`, `Cache-Control: no-cache`, and
`X-Content-Type-Options: nosniff`. The Companion response must have
`script-src 'self'` and `style-src 'self'` without `unsafe-inline`; Classic
retains its existing CSP because its current document still contains inline
code.

- [ ] **Step 2: Run the route tests and verify the expected failures**

Run:

```powershell
py -3.11 -m pytest tests/test_nova_companion_routes.py -q
```

Expected: failures because `_companion_ui_config`, `COMPANION_WEB_HTML`,
`/companion`, and `/classic` do not exist.

- [ ] **Step 3: Add the minimal semantic Companion document**

Create `nova_companion_web.html` with:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta name="theme-color" content="#0b0b18">
  <title>Nova Companion</title>
  <link rel="manifest" href="/manifest.webmanifest">
  <link rel="stylesheet" href="/assets/nova_companion/companion-shell.css">
</head>
<body>
  <main id="companionApp" aria-busy="true">
    <h1>Nova Companion</h1>
    <p id="companionBootStatus" role="status">Connecting to Nova…</p>
    <a href="/classic">Open Nova Classic</a>
  </main>
  <script src="/assets/nova_foundation_ui.js"></script>
  <script type="module" src="/assets/nova_companion/companion-app.js"></script>
</body>
</html>
```

Do not add inline event handlers, inline scripts, remote assets, or application
logic to this file.

- [ ] **Step 4: Implement configuration and HTML selection**

Extend `_runtime_cognitive_config()` with:

```python
"companion_ui": {
    "enabled": boolean("NOVA_COMPANION_ENABLED", True),
    "default": boolean("NOVA_COMPANION_DEFAULT", False),
},
```

Add:

```python
def _companion_ui_config():
    projected = _runtime_cognitive_config().get("companion_ui") or {}
    return {
        "enabled": bool(projected.get("enabled", True)),
        "default": bool(projected.get("default", False)),
    }
```

Load `COMPANION_WEB_HTML` once beside `WEB_HTML`. Add a private
`_send_html_document(document: str, *, companion: bool = False)` handler method
that applies the existing security headers. When `companion=True`, use this
stricter policy:

```text
default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'self';
script-src 'self'; style-src 'self'; img-src 'self' data: blob:;
media-src 'self' data: blob:; connect-src 'self'; worker-src 'self'
```

Classic keeps the current policy. Route behavior must be:

```python
if parsed.path in ("/", "/index.html"):
    config = _companion_ui_config()
    use_companion = config["enabled"] and config["default"]
    document = COMPANION_WEB_HTML if use_companion else WEB_HTML
    self._send_html_document(document, companion=use_companion)
elif parsed.path == "/classic":
    self._send_html_document(WEB_HTML)
elif parsed.path == "/companion" and _companion_ui_config()["enabled"]:
    self._send_html_document(COMPANION_WEB_HTML, companion=True)
```

Return a normal 404 for disabled `/companion`.

- [ ] **Step 5: Register the planned static asset allowlist**

Add all eleven `/assets/nova_companion/*.js` and
`/assets/nova_companion/companion-shell.css` entries to
`FoundationHttpController.UI_ASSETS`. Each entry must resolve beneath
`application_root`, use either `application/javascript; charset=utf-8` or
`text/css; charset=utf-8`, and receive the controller's normal security
headers.

For this task only, create empty-but-valid module files containing `export {};`
and a CSS file containing the root background token so the allowlisted routes
return 200. Later tasks replace their contents.

- [ ] **Step 6: Add safe defaults to both current configuration files**

Add:

```text
NOVA_COMPANION_ENABLED=true
NOVA_COMPANION_DEFAULT=false
```

to `.nova_llm_config`, and the equivalent boolean keys to
`nova_llm_config.json`. Do not change any other current configuration value.

- [ ] **Step 7: Run focused and existing route/security tests**

Run:

```powershell
py -3.11 -m pytest tests/test_nova_companion_routes.py tests/test_nova_foundation.py tests/test_nova_enhanced_server.py -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit only the HTTP boundary**

```powershell
git add -- nova_companion_web.html nova_enhanced_server.py src/nova_foundation_http.py .nova_llm_config nova_llm_config.json tests/test_nova_companion_routes.py assets/nova_companion
git commit -m "feat: add safe Nova Companion shell boundary"
```

---

### Task 2: Build the Living Cosmos Shell and Semantic Layout

**Files:**
- Modify: `nova_companion_web.html`
- Modify: `assets/nova_companion/companion-shell.css`
- Create: `tests/test_nova_companion_source.py`

**Interfaces:**
- Consumes: the `/companion` asset boundary from Task 1.
- Produces: stable element IDs and CSS classes used by every later browser module.

- [ ] **Step 1: Write failing semantic and security source tests**

```python
def test_companion_document_has_required_landmarks():
    html = (ROOT / "nova_companion_web.html").read_text(encoding="utf-8")
    for required in (
        'id="novaPresence"',
        'id="conversationTimeline"',
        'id="companionComposer"',
        'id="novaSparkButton"',
        'id="companionSheetHost"',
        'id="companionTrustButton"',
        'id="companionLiveStatus"',
        'href="/classic"',
    ):
        assert required in html
    assert "onclick=" not in html
    assert "innerHTML" not in html
    assert "http://" not in html
    assert "https://" not in html


def test_companion_css_has_mobile_accessibility_contract():
    css = (ROOT / "assets/nova_companion/companion-shell.css").read_text(encoding="utf-8")
    assert "env(safe-area-inset-bottom)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert ":focus-visible" in css
    assert "min-height: 44px" in css
    assert "overflow-x: hidden" in css
```

- [ ] **Step 2: Run the source tests and verify they fail**

```powershell
py -3.11 -m pytest tests/test_nova_companion_source.py -q
```

Expected: failures for missing semantic landmarks and CSS contracts.

- [ ] **Step 3: Replace the boot document with the stable shell**

The body must contain:

```html
<main class="companion-shell" id="companionApp" aria-busy="true">
  <header class="companion-topbar">
    <a class="companion-wordmark" href="/companion" aria-label="Nova Companion home">Nova</a>
    <button id="companionTrustButton" type="button" aria-controls="companionSheetHost">
      <span aria-hidden="true" class="local-dot"></span>
      <span id="companionTrustLabel">Checking privacy</span>
    </button>
  </header>
  <section id="novaPresence" aria-labelledby="novaGreeting">
    <div id="novaFace" aria-hidden="true">
      <span class="nova-eye"></span><span class="nova-eye"></span><span class="nova-mouth"></span>
    </div>
    <h1 id="novaGreeting">Nova is here.</h1>
    <p id="novaContinuityCue"></p>
  </section>
  <section id="conversationTimeline" aria-label="Conversation with Nova" aria-live="polite"></section>
  <p id="companionLiveStatus" class="sr-only" role="status"></p>
  <form id="companionComposer">
    <label class="sr-only" for="companionInput">Talk to Nova</label>
    <textarea id="companionInput" rows="1" maxlength="12000" placeholder="Talk to Nova…"></textarea>
    <button id="companionSendButton" type="submit" aria-label="Send message">↑</button>
  </form>
  <button id="novaSparkButton" type="button" aria-expanded="false" aria-controls="companionSheetHost">
    <span aria-hidden="true">✦</span><span class="sr-only">Open Nova Spark</span>
  </button>
  <div id="companionSheetBackdrop" hidden></div>
  <section id="companionSheetHost" role="dialog" aria-modal="true" aria-label="Nova capabilities" hidden></section>
  <a class="classic-fallback" href="/classic">Nova Classic</a>
</main>
```

The timeline remains outside the live status region so screen readers do not
re-read every streaming delta.

- [ ] **Step 4: Implement tokenized Living Cosmos CSS**

Define exact token families under `:root`: canvas, surface, surface-elevated,
text, text-muted, violet, cyan, success, warning, danger, focus, radius,
shadow, spacing, and safe-area values. Build:

- a fixed `100dvh` shell with `min-height: 0`;
- a scrollable timeline;
- an anchored composer padded by `env(safe-area-inset-bottom)`;
- full and compact presence layouts selected by `[data-presence-size]`;
- 44-pixel controls;
- bottom-sheet and Nova Spark states;
- `.sr-only`;
- visible `:focus-visible`;
- reduced-motion overrides that set animation duration to zero and preserve
  state labels;
- a single-column desktop adaptation with a centered maximum width rather than
  a separate desktop app.

Do not use `100vw`, fixed content widths, or `position: fixed` for the
composer. These are the common sources of the current mobile overflow bug.

- [ ] **Step 5: Run the source and route tests**

```powershell
py -3.11 -m pytest tests/test_nova_companion_source.py tests/test_nova_companion_routes.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit the shell**

```powershell
git add -- nova_companion_web.html assets/nova_companion/companion-shell.css tests/test_nova_companion_source.py
git commit -m "feat: add Living Cosmos companion shell"
```

---

### Task 3: Implement the Truthful State Reducer and Evolved Nova

**Files:**
- Modify: `assets/nova_companion/companion-store.js`
- Modify: `assets/nova_companion/companion-presence.js`
- Create: `tests/js/companion-store.test.mjs`
- Create: `tests/test_nova_companion_javascript.py`

**Interfaces:**
- Produces:
  - `COMPANION_PHASES: ReadonlySet<string>`
  - `createInitialCompanionState(options) -> CompanionState`
  - `reduceCompanionState(state, event) -> CompanionState`
  - `presenceViewModel(state, reducedMotion) -> PresenceViewModel`
  - `renderPresence(elements, viewModel) -> void`
- Consumes: no DOM in the reducer; `renderPresence` consumes explicit element references.

- [ ] **Step 1: Add the Python Node-test bridge**

```python
def test_companion_javascript_unit_suite():
    node = shutil.which("node")
    assert node, "Node.js is required to run Nova Companion's DOM-free unit tests"
    test_files = sorted((ROOT / "tests" / "js").glob("*.test.mjs"))
    assert test_files, "Nova Companion JavaScript tests were not found"
    completed = subprocess.run(
        [node, "--test", *[str(path) for path in test_files]],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
```

The test must fail rather than skip when Node is absent on a release machine.

- [ ] **Step 2: Write failing reducer and presence tests**

```javascript
test("cancelled requests ignore late deltas", () => {
  const initial = createInitialCompanionState({ clientId: "phone", conversationId: "conv-1" });
  const submitted = reduceCompanionState(initial, { type: "SUBMIT", requestId: "req-1", text: "Hello" });
  const cancelled = reduceCompanionState(submitted, { type: "CANCELLED", requestId: "req-1" });
  const late = reduceCompanionState(cancelled, { type: "DELTA", requestId: "req-1", delta: "late" });
  assert.equal(late.phase, "cancelled");
  assert.equal(late.streamingText, "");
});

test("a tool is acting only after an observed tool-start event", () => {
  const state = createInitialCompanionState({});
  const proposed = reduceCompanionState(state, { type: "TOOL_PROPOSED", requestId: "r", toolName: "vision.observe" });
  assert.notEqual(proposed.phase, "acting");
  const acting = reduceCompanionState(proposed, { type: "TOOL_STARTED", requestId: "r", toolName: "vision.observe" });
  assert.equal(acting.phase, "acting");
});

test("presence labels match real phases", () => {
  const thinking = presenceViewModel({ phase: "thinking", conversationTurnCount: 2 }, false);
  assert.equal(thinking.label, "Nova is thinking");
  assert.equal(thinking.size, "compact");
  assert.equal(thinking.motion, "thinking");
});
```

- [ ] **Step 3: Run the JavaScript bridge and verify it fails**

```powershell
py -3.11 -m pytest tests/test_nova_companion_javascript.py -q
```

Expected: Node reports missing exports.

- [ ] **Step 4: Implement the reducer**

`createInitialCompanionState()` must return a frozen-shape object containing:

```javascript
{
  phase: "booting",
  clientId: "",
  conversationId: "",
  activeRequestId: "",
  acceptedRequestIds: [],
  conversationTurnCount: 0,
  streamingText: "",
  activeTool: null,
  error: null,
  offline: false,
  sheet: null,
  camera: { permission: "unknown", active: false, persisted: false },
  microphone: { permission: "unknown", active: false },
  trust: { local: null, provider: "", model: "", memoryUsed: false }
}
```

The reducer must:

- accept only named events listed in the module;
- copy state rather than mutate it;
- ignore request-bound events whose `requestId` is not active;
- keep a bounded last-20 accepted request ID list;
- distinguish `submitting`, `thinking`, `acting`, `responding`, `completed`,
  `offline`, `failed`, and `cancelled`;
- never change `phase` to `completed` on `TOOL_PROPOSED` or `TOOL_STARTED`;
- clear private transient state when the conversation identity changes.

- [ ] **Step 5: Implement the presence view model and renderer**

`presenceViewModel()` maps phases to truthful labels, color names, face motion,
and `full|compact` size. `renderPresence()` sets `dataset.phase`,
`dataset.presenceSize`, text via `textContent`, and `aria-busy`; it never
accepts HTML. In reduced-motion mode it returns `motion: "none"`.

- [ ] **Step 6: Run JavaScript and source tests**

```powershell
py -3.11 -m pytest tests/test_nova_companion_javascript.py tests/test_nova_companion_source.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit the state and presence layer**

```powershell
git add -- assets/nova_companion/companion-store.js assets/nova_companion/companion-presence.js tests/js/companion-store.test.mjs tests/test_nova_companion_javascript.py
git commit -m "feat: add truthful Nova companion states"
```

---

### Task 4: Implement Authenticated Chat Streaming, Cancellation, and Recovery

**Files:**
- Modify: `assets/nova_companion/companion-api.js`
- Create: `tests/js/companion-api.test.mjs`

**Interfaces:**
- Consumes: existing global `authHeaders()`, `POST /nova/v1/chat`, `POST /nova/v1/cancel/{request_id}`, `GET /status`, and `GET /healthz`.
- Produces:
  - `createRequestId() -> string`
  - `parseSseBlock(block) -> object | null`
  - `NovaCompanionApi`
  - `NovaApiError extends Error`

- [ ] **Step 1: Write failing API tests**

```javascript
test("SSE parsing ignores heartbeats and returns deltas once", async () => {
  const fetchImpl = makeStreamingFetch([
    'event: response.heartbeat\ndata: {"event_type":"response.heartbeat"}\n\n',
    'event: response.delta\ndata: {"event_type":"response.delta","delta":"Hello "}\n\n',
    'event: response.delta\ndata: {"event_type":"response.delta","delta":"there"}\n\n',
    'event: response.completed\ndata: {"event_type":"response.completed","done":true,"metadata":{"trace":{"source":"nova_core"}}}\n\n',
    "data: [DONE]\n\n",
  ]);
  const deltas = [];
  const api = new NovaCompanionApi({ fetchImpl, authHeaders: extra => extra });
  const result = await api.streamChat({ text: "Hi", requestId: "req-1" }, { onDelta: value => deltas.push(value) });
  assert.deepEqual(deltas, ["Hello ", "there"]);
  assert.equal(result.text, "Hello there");
  assert.equal(result.trace.source, "nova_core");
});

test("pairing errors retain a machine-readable code", async () => {
  const api = new NovaCompanionApi({ fetchImpl: makeJsonFetch(401, { code: "pairing_required", error: "Pair first" }), authHeaders: extra => extra });
  await assert.rejects(() => api.getStatus(), error => error.code === "pairing_required" && error.status === 401);
});

test("one SSE block returns one parsed event", () => {
  assert.deepEqual(
    parseSseBlock('event: response.delta\ndata: {"event_type":"response.delta","delta":"Hi"}'),
    { event_type: "response.delta", delta: "Hi" }
  );
  assert.equal(parseSseBlock("data: [DONE]"), null);
});

test("cancel sends the server request id before aborting locally", async () => {
  const calls = [];
  const api = new NovaCompanionApi({ fetchImpl: recordingFetch(calls), authHeaders: extra => extra });
  await api.cancel("req-22");
  assert.equal(calls[0].url, "/nova/v1/cancel/req-22");
  assert.equal(calls[0].options.method, "POST");
});
```

- [ ] **Step 2: Run the API unit tests and verify they fail**

```powershell
node --test tests/js/companion-api.test.mjs
```

Expected: missing API exports.

- [ ] **Step 3: Implement the API service**

`NovaCompanionApi` constructor:

```javascript
constructor({
  baseUrl = window.location.origin,
  fetchImpl = globalThis.fetch.bind(globalThis),
  authHeaders = globalThis.authHeaders || (extra => ({ ...extra })),
  requestTimeoutMs = 120000
} = {})
```

Required methods:

```javascript
getStatus({ signal } = {})
getHealth({ signal } = {})
streamChat({ text, requestId, clientId, conversationId, sessionId, history = [] }, callbacks = {})
chat(body, { signal } = {})
cancel(requestId)
postVision(body, { signal } = {})
postTts(text, { signal, force = false } = {})
getJson(path, { signal } = {})
postJson(path, body, { signal } = {})
```

`streamChat()` must use the exact current request fields:

```javascript
{
  model: "nova",
  text,
  stream: true,
  request_id: requestId,
  client_id: clientId,
  conversation_id: conversationId,
  session_id: sessionId,
  recent_messages: history
}
```

It must normalize CRLF, parse complete double-newline SSE blocks, consume the
final buffer once, ignore `[DONE]`, preserve partial text on error, and require
a final `done` event. It must never resend automatically after an ambiguous
disconnect.

- [ ] **Step 4: Implement safe error normalization**

`NovaApiError` carries `status`, `code`, `partialText`, `requestId`, and a safe
message. It must not include the Authorization header, request body, prompt,
image base64, or stack trace in its serialized form.

- [ ] **Step 5: Run API and gateway streaming tests**

```powershell
node --test tests/js/companion-api.test.mjs
py -3.11 -m pytest tests/test_nova_gateway_http.py -q
```

Expected: all tests pass and the existing gateway streaming contract remains
unchanged.

- [ ] **Step 6: Commit the API service**

```powershell
git add -- assets/nova_companion/companion-api.js tests/js/companion-api.test.mjs
git commit -m "feat: add Nova companion streaming API client"
```

---

### Task 5: Integrate Conversation, Composer, Adaptive Presence, and Draft Recovery

**Files:**
- Modify: `assets/nova_companion/companion-conversation.js`
- Modify: `assets/nova_companion/companion-composer.js`
- Modify: `assets/nova_companion/companion-app.js`
- Modify: `assets/nova_companion/companion-shell.css`
- Modify: `tests/js/companion-store.test.mjs`
- Modify: `tests/test_nova_companion_source.py`

**Interfaces:**
- Consumes: `NovaCompanionApi`, the Task 3 reducer, `presenceViewModel`, and stable Task 2 DOM IDs.
- Produces:
  - `appendMessage(timeline, message) -> HTMLElement`
  - `beginStreamingMessage(timeline, responseId) -> HTMLElement`
  - `appendStreamingDelta(element, delta) -> void`
  - `createComposerController(options)`
  - a working `/companion` chat experience.

- [ ] **Step 1: Write failing conversation safety tests**

Add source tests asserting:

```python
conversation = (ROOT / "assets/nova_companion/companion-conversation.js").read_text(encoding="utf-8")
app = (ROOT / "assets/nova_companion/companion-app.js").read_text(encoding="utf-8")
assert "textContent" in conversation
assert ".innerHTML" not in conversation
assert "nova_companion_draft_v1" in app
assert "nova_companion_messages" not in app
assert "localStorage.setItem" not in conversation
```

Add reducer tests proving the presence is `full` at zero turns and `compact`
after the first completed user/Nova turn.

- [ ] **Step 2: Run the tests and verify they fail**

```powershell
py -3.11 -m pytest tests/test_nova_companion_source.py tests/test_nova_companion_javascript.py -q
```

Expected: missing rendering and draft behavior.

- [ ] **Step 3: Implement safe message rendering**

`appendMessage()`, `beginStreamingMessage()`, and `appendStreamingDelta()` must
render the following message objects:

```javascript
{
  id: "msg_*",
  role: "user" | "assistant" | "tool" | "system",
  text: "",
  status: "pending" | "streaming" | "completed" | "failed" | "cancelled",
  answerStatus: null,
  artifact: null
}
```

Create all nodes with `document.createElement()` and assign content with
`textContent`. Convert URLs to safe anchors only through a function that accepts
`http:` and `https:` and sets `target="_blank"` plus
`rel="noopener noreferrer"`. Do not render HTML returned by Nova.

- [ ] **Step 4: Implement composer behavior**

`createComposerController()` must:

- submit on Enter and insert a newline on Shift+Enter;
- disable double submission;
- change the send control into Stop while a request is active;
- retain the current draft under `nova_companion_draft_v1`;
- delete the draft only after the server accepts the request;
- restore focus without forcing the mobile keyboard after navigation;
- resize the textarea to a bounded maximum height;
- call server cancellation before aborting the local controller.

Only the unsent draft, a generated client ID, and a generated conversation ID
may use localStorage. Messages remain server/memory owned and are not persisted
by the new shell.

- [ ] **Step 5: Coordinate the application lifecycle**

`companion-app.js` must:

1. read or generate `clientId` and `conversationId`;
2. create the API and reducer store;
3. check `/status`;
4. render `present`, `offline`, or pairing-required state;
5. wire the composer;
6. render one pending user message;
7. consume streaming deltas exactly once;
8. render the final answer status and permission snapshot;
9. update Adaptive Presence after the completed turn;
10. expose Retry without automatic resubmission on ambiguous failures.

The boot process must retain a visible `/classic` link if any module fails.

- [ ] **Step 6: Run focused tests**

```powershell
py -3.11 -m pytest tests/test_nova_companion_source.py tests/test_nova_companion_javascript.py tests/test_nova_gateway_http.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Live-test one deterministic chat turn**

Start Nova on the normal local port, open `/companion`, send
`"Yo, what is up?"`, and verify:

- one user bubble;
- one Nova bubble;
- no duplicated delta;
- `Present -> Thinking -> Responding -> Completed`;
- Adaptive Presence becomes compact;
- the composer remains visible;
- Nova Classic link works.

Record the response time and screenshot path in the task notes.

- [ ] **Step 8: Commit the first usable Companion slice**

```powershell
git add -- assets/nova_companion/companion-app.js assets/nova_companion/companion-conversation.js assets/nova_companion/companion-composer.js assets/nova_companion/companion-shell.css tests/js/companion-store.test.mjs tests/test_nova_companion_source.py
git commit -m "feat: add adaptive Nova companion chat"
```

---

### Task 6: Add the Accessible Nova Spark Capability Layer

**Files:**
- Modify: `assets/nova_companion/companion-spark.js`
- Modify: `assets/nova_companion/companion-app.js`
- Modify: `assets/nova_companion/companion-shell.css`
- Modify: `assets/nova_foundation_ui.js:797-815`
- Create: `tests/js/companion-spark.test.mjs`
- Modify: `tests/test_nova_companion_source.py`
- Modify: `tests/test_nova_desktop_experience.py`

**Interfaces:**
- Consumes: `GET /nova/v1/capabilities`, `GET /nova/v1/tools`, current `openPanel(panelId)`, and the Companion sheet host.
- Produces:
  - `COMPANION_CAPABILITIES`
  - `resolveSparkActions(serverItems, registry)`
  - `resolveCapabilityAvailability(capability, serverState)`
  - `classicPanelUrl(panelName)`
  - `createSparkController(options)`

- [ ] **Step 1: Write failing capability tests**

```javascript
test("the model cannot add an unregistered Spark action", () => {
  const shown = resolveSparkActions(
    [{ id: "chat", available: true }, { id: "invented-shell", available: true }],
    COMPANION_CAPABILITIES
  );
  assert.deepEqual(shown.map(item => item.id), ["chat"]);
});

test("classic panel URLs use an allowlist", () => {
  assert.equal(classicPanelUrl("memory"), "/classic?panel=memory");
  assert.equal(classicPanelUrl("../../settings"), "/classic");
});

test("unavailable capabilities remain visible with a reason", () => {
  const item = resolveCapabilityAvailability(
    { id: "vision", requiredCapability: "vision.image_input" },
    { capabilities: {} }
  );
  assert.equal(item.available, false);
  assert.equal(item.reason, "Vision is not available on this Nova server.");
});
```

- [ ] **Step 2: Run Spark tests and verify they fail**

```powershell
node --test tests/js/companion-spark.test.mjs
```

Expected: missing registry and resolver exports.

- [ ] **Step 3: Implement the fixed capability registry**

Each registry entry contains:

```javascript
{
  id: "vision",
  group: "see",
  label: "See with camera",
  description: "Let Nova inspect a picture or live frame.",
  icon: "◎",
  mode: "companion" | "classic",
  panel: "display",
  requiredCapability: "vision.image_input",
  requiredPermission: "camera"
}
```

Implement the approved See, Speak, Create, Remember, Work, and System groups.
Server capability and tool responses may change availability and reason text;
they may not add IDs absent from this registry.

- [ ] **Step 4: Implement the accessible Spark controller**

`createSparkController()` must:

- open by click, Enter, Space, or a supplied voice command;
- use `aria-expanded`;
- trap focus only while the modal sheet is open;
- close on Escape, backdrop click, or successful navigation;
- restore focus to the Spark button;
- display a dismissible discovery hint for the first three opens;
- retain text labels beside icons;
- leave the sheet open when an action fails to resolve.

- [ ] **Step 5: Expand the existing Classic query-panel allowlist**

Replace the current two-case query handling with an explicit mapping:

```javascript
const requestedPanels = {
  chat: "chat-panel",
  settings: "settings-panel",
  display: "display-panel",
  dream: "dream-studio-panel",
  agents: "agent-library-panel",
  builder: "app-builder-panel",
  memory: "memory-panel",
  tools: "tools-panel",
  research: "research-panel",
  tests: "test-check-panel",
  projects: "saved-projects-panel",
  files: "file-manager-panel",
  logs: "debug-logs-panel"
};
```

Unknown values open Classic without selecting a panel. Add tests that every
mapped panel ID exists in `nova_chat_web.html`.

- [ ] **Step 6: Run focused tests and live-test touch navigation**

```powershell
node --test tests/js/companion-spark.test.mjs
py -3.11 -m pytest tests/test_nova_companion_source.py tests/test_nova_desktop_experience.py -q
```

At `390x844`, open Spark, activate Memory, verify `/classic?panel=memory`
selects the existing Memory panel, then return to `/companion`.

- [ ] **Step 7: Commit Nova Spark**

```powershell
git add -- assets/nova_companion/companion-spark.js assets/nova_companion/companion-app.js assets/nova_companion/companion-shell.css assets/nova_foundation_ui.js tests/js/companion-spark.test.mjs tests/test_nova_companion_source.py tests/test_nova_desktop_experience.py
git commit -m "feat: add accessible Nova Spark navigation"
```

---

### Task 7: Add Truthful Picture and Live-Camera Vision

**Files:**
- Modify: `assets/nova_companion/companion-senses.js`
- Modify: `assets/nova_companion/companion-app.js`
- Modify: `assets/nova_companion/companion-shell.css`
- Create: `tests/js/companion-senses.test.mjs`
- Modify: `tests/test_nova_companion_source.py`

**Interfaces:**
- Consumes: existing `POST /api/chat` permission command, `POST /api/vision`, browser `getUserMedia`, and `NovaCompanionApi.postVision()`.
- Produces:
  - `prepareVisionCanvas(source, options) -> VisionFrame`
  - `buildVisionPayload(frame, prompt) -> object`
  - `visionStateAfter(state, event) -> VisionState`
  - `createVisionController(options)`

- [ ] **Step 1: Write failing deterministic vision tests**

```javascript
test("vision payload declares local preprocessing and no persistence", () => {
  const payload = buildVisionPayload(
    { filename: "camera-frame.jpg", mimeType: "image/jpeg", imageBase64: "abc", width: 640, height: 480, resized: true },
    "What is in front of me?"
  );
  assert.equal(payload.mime_type, "image/jpeg");
  assert.equal(payload.client_processing.width, 640);
  assert.equal(payload.client_processing.height, 480);
  assert.equal(payload.client_processing.resized, true);
  assert.equal(payload.persist, false);
});

test("camera state is not active before a stream exists", () => {
  const state = visionStateAfter({ type: "CAMERA_PERMISSION_GRANTED" });
  assert.equal(state.active, false);
  assert.equal(state.permission, "granted");
});
```

- [ ] **Step 2: Run the senses tests and verify they fail**

```powershell
node --test tests/js/companion-senses.test.mjs
```

Expected: missing vision functions.

- [ ] **Step 3: Implement picture selection and local preprocessing**

`prepareVisionCanvas()` must accept `image/jpeg`, `image/png`, and
`image/webp`. Decode through
`createImageBitmap` when available, resize the longest edge to at most 1280
pixels, encode JPEG at `0.82`, cap encoded bytes to the server's current limit,
and return only base64 plus deterministic dimensions and resize metadata.

Do not place image bytes in localStorage, IndexedDB, Cache Storage, logs, URL
parameters, or error messages.

- [ ] **Step 4: Implement explicit camera activation**

`createVisionController()` must enforce this sequence:

1. user opens See;
2. UI explains local processing and persistence state;
3. user taps Enable Camera;
4. Companion sends the existing `allow camera` Nova command;
5. browser requests `getUserMedia({video:{facingMode}, audio:false})`;
6. `camera.active` becomes true only after a live video track exists;
7. capture occurs only after the user taps Look;
8. Stop ends every track and clears the preview canvas.

Changing front/back camera must stop the old tracks before opening the new
stream.

- [ ] **Step 5: Render observed vision results truthfully**

Submit the existing `/api/vision` body fields used by
`nova_chat_web.html:4361-4393`. Render the result as a Nova message with
`answer_status`. Display OCR/model/basic-inspection metadata from the trace,
but never claim Moondream or OCR ran unless the trace says it did.

- [ ] **Step 6: Run automated and live picture tests**

```powershell
node --test tests/js/companion-senses.test.mjs
py -3.11 -m pytest tests/test_nova_companion_source.py tests/test_nova_enhanced_server.py -q
```

Live-test the user-supplied Nova phone screenshot and verify:

- Nova identifies the application;
- visible text is available through OCR;
- image persistence is false;
- camera state is obvious;
- no physical navigation is authorized;
- closing the sheet stops tracks.

- [ ] **Step 7: Commit Companion vision**

```powershell
git add -- assets/nova_companion/companion-senses.js assets/nova_companion/companion-app.js assets/nova_companion/companion-shell.css tests/js/companion-senses.test.mjs tests/test_nova_companion_source.py
git commit -m "feat: add truthful Nova companion vision"
```

---

### Task 8: Add Voice Conversation Without Faking Listening or Speaking

**Files:**
- Modify: `assets/nova_companion/companion-senses.js`
- Modify: `assets/nova_companion/companion-app.js`
- Modify: `assets/nova_companion/companion-presence.js`
- Modify: `tests/js/companion-senses.test.mjs`
- Modify: `tests/test_nova_companion_source.py`

**Interfaces:**
- Consumes: browser `SpeechRecognition` when available, existing `POST /api/tts`, HTMLAudioElement, and the normal chat submission path.
- Produces:
  - `createVoiceController(options)`
  - `voiceAvailability(windowLike) -> VoiceAvailability`
  - truthful `listening` and `responding` state events.

- [ ] **Step 1: Write failing voice-state tests**

```javascript
test("unsupported recognition never reports listening", () => {
  const availability = voiceAvailability({});
  assert.equal(availability.transcription, false);
  assert.equal(availability.reason, "Speech recognition is unavailable in this browser.");
});

test("audio is speaking only after the play event", () => {
  const events = [];
  const controller = createVoiceController({ dispatch: event => events.push(event), audioFactory: fakeAudio });
  controller.attachAudio(makeAudioThatHasNotPlayed());
  assert.equal(events.some(event => event.type === "SPEECH_STARTED"), false);
});
```

- [ ] **Step 2: Run the voice tests and verify they fail**

```powershell
node --test tests/js/companion-senses.test.mjs
```

Expected: missing voice exports.

- [ ] **Step 3: Implement microphone transcription**

Use `window.SpeechRecognition || window.webkitSpeechRecognition` only when
present. `LISTENING_STARTED` is dispatched from the engine's `onstart`, not
from the button click. Interim transcripts are visible but are not submitted.
The final transcript populates the composer and requires the user's normal
send action unless continuous Talk mode was explicitly enabled.

`onerror` maps `not-allowed`, `audio-capture`, `no-speech`, `network`, and
unknown failures to distinct safe messages. `onend` always clears listening
state.

- [ ] **Step 4: Implement server voice playback**

Call `NovaCompanionApi.postTts()` with the final Nova text. Create an audio data
URL from `mime_type` and `audio_base64`. Dispatch:

- `SPEECH_STARTED` only from `audio.onplay`;
- `SPEECH_FINISHED` from `audio.onended`;
- `SPEECH_FAILED` from `audio.onerror`.

Stop cancels recognition, pauses audio, clears its source, and cancels the
active chat request.

- [ ] **Step 5: Run automated and live voice tests**

```powershell
node --test tests/js/companion-senses.test.mjs
py -3.11 -m pytest tests/test_nova_companion_source.py -q
```

On the phone, verify permission denied, microphone unavailable, one successful
transcript, server TTS play, Stop, and text-chat fallback. Confirm the face
never shows listening before recognition starts or speaking before audio plays.

- [ ] **Step 6: Commit Companion voice**

```powershell
git add -- assets/nova_companion/companion-senses.js assets/nova_companion/companion-app.js assets/nova_companion/companion-presence.js tests/js/companion-senses.test.mjs tests/test_nova_companion_source.py
git commit -m "feat: add truthful Nova companion voice"
```

---

### Task 9: Add Pairing and the Privacy-Safe Trust Surface

**Files:**
- Modify: `assets/nova_companion/companion-trust.js`
- Modify: `assets/nova_companion/companion-app.js`
- Modify: `assets/nova_companion/companion-shell.css`
- Modify: `assets/nova_foundation_ui.js:1-35`
- Modify: `assets/nova_foundation_ui.js:835-857`
- Create: `tests/js/companion-trust.test.mjs`
- Modify: `tests/test_nova_companion_source.py`
- Modify: `tests/test_nova_foundation.py`

**Interfaces:**
- Consumes: existing `/api/pairing/status`, `/api/pairing/exchange`, `/status`, `/healthz`, `/nova/v1/health`, `authHeaders()`, and Foundation's validated token storage.
- Produces:
  - `projectTrustState(inputs) -> TrustState`
  - `redactTrustValue(key, value) -> safe value`
  - `createTrustController(options)`
  - inline remote-device pairing.

- [ ] **Step 1: Write failing trust and redaction tests**

```javascript
test("trust projection never copies private content", () => {
  const projected = projectTrustState({
    status: { private_mode: true, permissions: { camera: false } },
    health: { provider: "existing-nova", model: "nova", prompt: "secret prompt" },
    trace: { answer_status: { memory: "used" }, hidden_reasoning: "secret" }
  });
  assert.equal(projected.privateMode, true);
  assert.equal(projected.memoryUsed, true);
  assert.equal(JSON.stringify(projected).includes("secret"), false);
});

test("sensitive keys are always redacted", () => {
  for (const key of ["authorization", "api_key", "token", "prompt", "memory_content", "image_base64"]) {
    assert.equal(redactTrustValue(key, "secret"), "[redacted]");
  }
});
```

- [ ] **Step 2: Run trust tests and verify they fail**

```powershell
node --test tests/js/companion-trust.test.mjs
```

Expected: missing trust exports.

- [ ] **Step 3: Export the existing validated Foundation token helpers**

Expose `pairedDeviceToken` and `rememberPairedDeviceToken` in the existing
`Object.assign(global, ...)` block. Do not rename the storage key or accept
tokens that fail the existing `nova_` prefix validation.

Add Foundation tests proving:

- a valid exchanged token becomes available to `authHeaders`;
- invalid token text is rejected;
- the token never appears in status payloads.

- [ ] **Step 4: Implement inline pairing**

When any API call returns `401` with `code: pairing_required`, open a Companion
pairing sheet containing only device name and six-digit code. Exchange through
`POST /api/pairing/exchange`, pass the returned token to
`rememberPairedDeviceToken`, discard the code, and re-run status. Do not
automatically replay the user's prior chat request; show Retry after pairing.

- [ ] **Step 5: Implement the Trust projection**

`createTrustController()` must pass server inputs through
`projectTrustState()`. The visible Trust state contains only:

```javascript
{
  connection: "local" | "remote" | "offline",
  provider: "",
  model: "",
  privateMode: false,
  memoryUsed: false,
  camera: { active: false, persisted: false },
  microphone: { active: false },
  pendingConfirmation: false,
  estimatedCost: null,
  recentActions: []
}
```

Recent actions contain action name, state, and timestamp only. Never copy tool
arguments, prompts, memory text, file content, headers, or hidden reasoning.

- [ ] **Step 6: Run automated and live remote pairing tests**

```powershell
node --test tests/js/companion-trust.test.mjs
py -3.11 -m pytest tests/test_nova_foundation.py tests/test_nova_companion_source.py -q
```

Through the existing Cloudflare quick-tunnel path, verify an unpaired phone is
blocked, pairing succeeds once, chat becomes available, and Trust reports
Remote + Paired without displaying the token.

- [ ] **Step 7: Commit Trust and pairing**

```powershell
git add -- assets/nova_companion/companion-trust.js assets/nova_companion/companion-app.js assets/nova_companion/companion-shell.css assets/nova_foundation_ui.js tests/js/companion-trust.test.mjs tests/test_nova_companion_source.py tests/test_nova_foundation.py
git commit -m "feat: add Nova companion trust and pairing"
```

---

### Task 10: Make Companion Installable Without Caching Private Content

**Files:**
- Modify: `manifest.webmanifest`
- Modify: `service-worker.js`
- Modify: `offline.html`
- Create: `tests/test_nova_companion_pwa.py`

**Interfaces:**
- Consumes: `/companion`, `/classic`, the Companion static asset allowlist, and existing application icon.
- Produces: installable Companion start URL and a shell-only offline experience.

- [ ] **Step 1: Write failing PWA cache-boundary tests**

```python
def test_manifest_opens_companion_and_keeps_classic_shortcut():
    manifest = json.loads((ROOT / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["start_url"].startswith("/companion")
    assert any(item["url"] == "/classic" for item in manifest["shortcuts"])


def test_service_worker_caches_only_public_shell_assets():
    source = (ROOT / "service-worker.js").read_text(encoding="utf-8")
    assert "'/companion'" in source
    assert "'/classic'" not in source
    for forbidden in ("/api/", "/nova/", "/status", "/healthz", "image_base64", "conversation"):
        assert f"cache.put('{forbidden}'" not in source
    assert "isPrivateRuntimePath" in source
```

- [ ] **Step 2: Run PWA tests and verify they fail**

```powershell
py -3.11 -m pytest tests/test_nova_companion_pwa.py -q
```

Expected: manifest and service-worker assertions fail.

- [ ] **Step 3: Update the manifest**

Set `start_url` to `/companion?source=installed`. Keep the current icon. Add
shortcuts for Companion, Nova Classic, and Settings
(`/classic?panel=settings`). Preserve standalone display and current theme
colors adjusted to the Living Cosmos tokens.

- [ ] **Step 4: Replace broad navigation caching with explicit shell caching**

Add:

```javascript
function isPrivateRuntimePath(pathname){
  return pathname.startsWith("/api/")
    || pathname.startsWith("/nova/")
    || pathname === "/status"
    || pathname === "/health"
    || pathname === "/healthz";
}
```

Rules:

- never call `cache.put()` for private runtime paths;
- cache `/companion`, `offline.html`, manifest, icon, CSS, and Companion module
  assets only;
- use network-first for `/companion` navigation with cached Companion fallback;
- use `offline.html` for other failed navigations;
- never cache `/classic`, because its large generated HTML changes frequently;
- bump the cache name;
- delete older `nova-shell-*` caches on activation.

- [ ] **Step 5: Update offline recovery**

The offline page must explain that the shell cannot reach Nova, preserve no
private content, and provide Retry, `/companion`, and `/classic` links. It must
not claim Nova is thinking or responding.

- [ ] **Step 6: Run PWA and existing desktop tests**

```powershell
py -3.11 -m pytest tests/test_nova_companion_pwa.py tests/test_nova_desktop_experience.py tests/test_nova_reliability.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit PWA changes**

```powershell
git add -- manifest.webmanifest service-worker.js offline.html tests/test_nova_companion_pwa.py
git commit -m "feat: add private-safe Nova Companion PWA"
```

---

### Task 11: Run Mobile Accessibility, Performance, and Acceptance Gates

**Files:**
- Create: `tools/run_nova_companion_acceptance.py`
- Modify: `assets/nova_companion/companion-shell.css`
- Modify: `tests/test_nova_companion_source.py`
- Create: `reports/NOVA_COMPANION_RELEASE_AUDIT.md`

**Interfaces:**
- Consumes: live `/companion`, `/healthz`, `/nova/v1/chat`, the existing 560-case evaluation bank, and browser inspection.
- Produces: `reports/nova_companion_acceptance.json` and a release audit with measured rather than estimated results.

- [ ] **Step 1: Write the no-training HTTP acceptance runner**

The script must:

- accept `--base-url`, defaulting to `http://127.0.0.1:8765`;
- generate one client and conversation ID;
- check `/companion`, `/classic`, `/healthz`, `/nova/v1/capabilities`, and
  `/nova/v1/tools`;
- submit 25 evaluation-only turns covering greeting, affection, day check-in,
  follow-up, correction, relationship support, memory recall, current-fact
  honesty, uncertainty, interruption, and reconnect;
- fail on generic off-topic recovery phrases already listed in
  `src/nova_conversation_eval.py`;
- record latency, status, intent, memory use, safety state, and response length;
- hash `data/conversation_training_data.jsonl` before and after;
- fail if the hash changes;
- write JSON without prompt or response content.

The JSON entry schema is:

```python
{
    "case_id": "relationship_followup_01",
    "passed": True,
    "http_status": 200,
    "latency_ms": 412,
    "intent": "relationship",
    "memory_used": False,
    "safety_state": "passed",
    "response_length": 94,
}
```

- [ ] **Step 2: Add source-level accessibility and storage assertions**

Add assertions for:

- every sheet opener has `aria-controls`;
- the Spark button has accessible text;
- camera and microphone controls are real buttons;
- no `user-scalable=no`;
- no `maximum-scale=1`;
- no Companion module writes keys containing `message`, `history`, `prompt`,
  `image`, `audio`, `memory`, or `token`;
- no module logs request bodies or response text.

- [ ] **Step 3: Run the automated acceptance matrix**

```powershell
py -3.11 tools/run_nova_companion_acceptance.py --base-url http://127.0.0.1:8765 --output reports/nova_companion_acceptance.json
py -3.11 -m pytest tests/test_nova_companion_source.py tests/test_nova_companion_javascript.py tests/test_nova_companion_pwa.py -q
```

Expected:

- 25/25 turns pass;
- training hash unchanged;
- all Companion automated tests pass.

- [ ] **Step 4: Live-test at `390x844`**

Use the real in-app browser and verify:

- no horizontal body overflow is present;
- composer remains visible before and after keyboard focus;
- Adaptive Presence changes size without moving the composer;
- Spark opens, traps focus, closes with Escape, and restores focus;
- bottom sheet respects safe-area inset;
- 25-turn timeline scroll remains smooth;
- Stop cancels one live request;
- Classic fallback opens;
- camera and voice indicators are truthful.

Record viewport, computed dimensions, scroll positions, and screenshot paths in
the audit.

- [ ] **Step 5: Live-test at `430x932` and desktop**

Repeat the layout, Spark, composer, reduced-motion, and Classic checks at
`430x932` and at a desktop width of at least 1024 CSS pixels. Use keyboard-only
navigation on desktop.

- [ ] **Step 6: Measure performance**

Measure from navigation start to the shell's explicit
`data-companion-ready="true"` mark over the local network. Record median of
five warm runs. Record frame stability during presence motion and document any
device-specific limitation rather than claiming 60 fps without evidence.

- [ ] **Step 7: Fix only measured gate failures and rerun their checks**

Allowed fixes are bounded to Companion HTML, CSS, and modules. Do not weaken
assertions or change Nova's cognitive output to satisfy a visual gate. Each fix
must be followed by the smallest failing test and its parent task's focused
suite.

- [ ] **Step 8: Write the release audit**

`reports/NOVA_COMPANION_RELEASE_AUDIT.md` must include:

- exact files;
- route and feature-flag status;
- viewport results;
- accessibility results;
- performance measurements;
- 25-turn results;
- vision and voice results;
- training hash result;
- current known limitations;
- Classic rollback proof;
- whether Companion is ready to become default.

- [ ] **Step 9: Commit acceptance tooling and measured fixes**

```powershell
git add -- tools/run_nova_companion_acceptance.py reports/NOVA_COMPANION_RELEASE_AUDIT.md reports/nova_companion_acceptance.json assets/nova_companion/companion-shell.css tests/test_nova_companion_source.py
git commit -m "test: add Nova Companion release gates"
```

---

### Task 12: Run Full Regression, Document Rollback, and Decide the Default

**Files:**
- Modify: `docs/NOVA_COGNITIVE_OPERATING_LAYER.md`
- Modify: `reports/NOVA_COMPANION_RELEASE_AUDIT.md`
- Modify only after every gate passes: `.nova_llm_config`
- Modify only after every gate passes: `nova_llm_config.json`

**Interfaces:**
- Consumes: all prior tasks and the current full Nova test suite.
- Produces: a verified Companion release with a one-flag rollback and an honest default-state decision.

- [ ] **Step 1: Document the presentation boundary**

Add:

```text
External user
  -> Nova Companion or Nova Classic
  -> the same Nova API boundary
  -> the same cognitive core, identity, memory, tools, and model registry
```

Document `/companion`, `/classic`, both flags, PWA behavior, pairing, Trust,
and the exact rollback command/configuration. State explicitly that Companion
does not bypass Nova to call Ollama.

- [ ] **Step 2: Run all JavaScript tests**

```powershell
$testFiles = Get-ChildItem -LiteralPath tests/js -Filter '*.test.mjs' | Select-Object -ExpandProperty FullName
node --test @testFiles
```

Expected: zero failures.

- [ ] **Step 3: Run all focused Companion and HTTP suites**

```powershell
py -3.11 -m pytest tests/test_nova_companion_routes.py tests/test_nova_companion_source.py tests/test_nova_companion_javascript.py tests/test_nova_companion_pwa.py tests/test_nova_foundation.py tests/test_nova_gateway_http.py tests/test_nova_desktop_experience.py -q
```

Expected: zero failures.

- [ ] **Step 4: Run the entire existing and new suite**

```powershell
py -3.11 -m pytest -q
```

Expected: at least `1,323 passed`, exactly the preexisting skips unless a
platform capability legitimately changes, and zero failures. Record the exact
passing, skipped, failed, and elapsed totals in the audit.

- [ ] **Step 5: Re-run the 560-case conversation evaluation**

```powershell
py -3.11 tools/run_conversation_eval.py --output reports/nova_conversation_eval_v1.json
```

Expected: 560/560, zero training writes, prompt content logging false.

- [ ] **Step 6: Re-run live route and rollback proof**

Verify HTTP 200 for:

```text
/companion
/classic
/health
/healthz
/nova/v1/health
/v1/models
/nova/v1/providers
/nova/v1/capabilities
/nova/v1/tools
```

Set `NOVA_COMPANION_DEFAULT=false`, restart, and prove `/` serves Classic.
Set it to true only if the release audit has no failed gate, restart, and prove:

- `/` serves Companion;
- `/classic` serves the unchanged working interface;
- `/api/chat` and `/nova/v1/chat` still enter Nova Core.

- [ ] **Step 7: Make the default decision**

If and only if every gate passed, set:

```text
NOVA_COMPANION_ENABLED=true
NOVA_COMPANION_DEFAULT=true
```

in both configuration files and record `READY — DEFAULT ENABLED`.

If any gate failed, retain:

```text
NOVA_COMPANION_ENABLED=true
NOVA_COMPANION_DEFAULT=false
```

and record `PARTIAL — COMPANION AVAILABLE AT /companion`. Do not hide the
failed gate.

- [ ] **Step 8: Commit documentation and the verified default state**

```powershell
git add -- docs/NOVA_COGNITIVE_OPERATING_LAYER.md reports/NOVA_COMPANION_RELEASE_AUDIT.md .nova_llm_config nova_llm_config.json
git commit -m "docs: release Nova Companion with verified rollback"
```

- [ ] **Step 9: Final handoff**

Report:

- the live local Companion and Classic links;
- the active remote link if the user explicitly requested a temporary tunnel;
- exact test totals;
- 560-case evaluation total;
- 25-turn acceptance total;
- measured shell timing;
- phone viewport results;
- voice and vision status;
- default flag state;
- exact rollback steps;
- known limitations;
- confirmation that no model, adapter, checkpoint, training, identity, memory,
  tool, or API behavior was replaced.
