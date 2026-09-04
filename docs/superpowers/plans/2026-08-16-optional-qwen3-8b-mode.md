# Optional Qwen 3 8B Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `qwen3:8b` as an explicit Nova Strong mode while retaining `qwen2.5:3b` as the reliable default.

**Architecture:** The browser sends the named mode `strong`; it never sends an arbitrary model identifier. A server helper maps that allowlisted mode to configured local model settings, checks provider availability and quarantine state, and applies a primary-model override only for model-generated Nova replies. If the optional model cannot run, the ordinary managed route remains available.

**Tech Stack:** Python 3, pytest, browser JavaScript embedded in `nova_chat_web.html`, Ollama's existing local provider, JSON and environment-style configuration.

## Global Constraints

- Keep `NOVA_DEEP_LOCAL_LLM_MODEL=qwen2.5:3b` and `NOVA_ACTIVE_BRAIN=qwen2.5:3b` unchanged.
- Do not unload unrelated running models automatically.
- Keep Nova identity, conversation context, memory, tools, validation, and safety active in Strong mode.
- Keep Raw Qwen and Raw Dolphin behavior unchanged.
- Accept only the named browser mode `strong`; do not accept a browser-supplied arbitrary model name.
- Fall back to ordinary Nova routing if the optional model is unavailable or quarantined.

---

## File map

- `src/nova_local_llm_connector.py`: owns defaults and typed accessors for the optional model, timeout, and keep-alive.
- `.nova_llm_config` and `nova_llm_config.json`: select the locally installed `qwen3:8b` without changing Nova's current default/deep model.
- `nova_enhanced_server.py`: validates the named mode, resolves local availability, applies the managed override, and records a safe trace.
- `nova_chat_web.html`: stores the selected managed mode, renders the selector/status, and sends `nova_model_mode`.
- `tests/test_nova_local_llm_config.py`: proves the optional settings load with the intended values.
- `tests/test_nova_enhanced_server.py`: proves allowlisting, fallback, routing precedence, and browser payload behavior.

### Task 1: Optional strong-model configuration

**Files:**
- Modify: `src/nova_local_llm_connector.py`
- Modify: `.nova_llm_config`
- Modify: `nova_llm_config.json`
- Test: `tests/test_nova_local_llm_config.py`

**Interfaces:**
- Produces: `LocalLLMConfig.optional_strong_model -> str`
- Produces: `LocalLLMConfig.optional_strong_timeout -> int`
- Produces: `LocalLLMConfig.optional_strong_keep_alive -> str`

- [ ] **Step 1: Write the failing configuration test**

Add a focused test without altering assertions for Nova's existing default models:

```python
def test_optional_strong_model_configuration_is_explicit_and_does_not_replace_default():
    config = llm.LocalLLMConfig()
    env_config = (ROOT / ".nova_llm_config").read_text(encoding="utf-8")
    json_config = json.loads((ROOT / "nova_llm_config.json").read_text(encoding="utf-8"))

    assert config.optional_strong_model == "qwen3:8b"
    assert config.optional_strong_timeout == 240
    assert config.optional_strong_keep_alive == "5m"
    assert "NOVA_OPTIONAL_STRONG_MODEL=qwen3:8b" in env_config
    assert json_config["NOVA_OPTIONAL_STRONG_MODEL"] == "qwen3:8b"
    assert json_config["NOVA_OPTIONAL_STRONG_TIMEOUT"] == 240
    assert json_config["NOVA_OPTIONAL_STRONG_KEEP_ALIVE"] == "5m"
    assert config.deep_model != config.optional_strong_model
```

- [ ] **Step 2: Run the test and confirm the missing-property failure**

Run: `python -m pytest tests/test_nova_local_llm_config.py::test_optional_strong_model_configuration_is_explicit_and_does_not_replace_default -q`

Expected: FAIL with `AttributeError: 'LocalLLMConfig' object has no attribute 'optional_strong_model'`.

- [ ] **Step 3: Add the minimal settings and accessors**

Add to `LocalLLMConfig.DEFAULT_CONFIG`:

```python
"NOVA_OPTIONAL_STRONG_MODEL": "qwen3:8b",
"NOVA_OPTIONAL_STRONG_TIMEOUT": 240,
"NOVA_OPTIONAL_STRONG_KEEP_ALIVE": "5m",
```

Add these properties beside the other model properties:

```python
@property
def optional_strong_model(self) -> str:
    return str(self.config.get("NOVA_OPTIONAL_STRONG_MODEL", "qwen3:8b") or "qwen3:8b")

@property
def optional_strong_timeout(self) -> int:
    return max(30, min(int(self.config.get("NOVA_OPTIONAL_STRONG_TIMEOUT", 240) or 240), 600))

@property
def optional_strong_keep_alive(self) -> str:
    return str(self.config.get("NOVA_OPTIONAL_STRONG_KEEP_ALIVE", "5m") or "5m")
```

Add the three exact values to `.nova_llm_config` and `nova_llm_config.json`. Do not edit either current 3B default/deep line.

- [ ] **Step 4: Run the focused test and the local-configuration file**

Run: `python -m pytest tests/test_nova_local_llm_config.py::test_optional_strong_model_configuration_is_explicit_and_does_not_replace_default -q`

Expected: PASS.

Run: `python -m pytest tests/test_nova_local_llm_config.py -q`

Expected: all tests in the file PASS; if a pre-existing assertion conflicts with the already-approved 3B configuration, report that baseline mismatch separately instead of reverting the 3B configuration.

- [ ] **Step 5: Commit the configuration unit**

```powershell
git add -- src/nova_local_llm_connector.py .nova_llm_config nova_llm_config.json tests/test_nova_local_llm_config.py
git commit -m "feat: configure optional qwen3 8b mode"
```

### Task 2: Allowlisted managed server route

**Files:**
- Modify: `nova_enhanced_server.py`
- Test: `tests/test_nova_enhanced_server.py`

**Interfaces:**
- Consumes: the three `LocalLLMConfig.optional_strong_*` properties from Task 1.
- Produces: `_optional_strong_model_decision(context: dict | None, raw_adapter_request: bool = False) -> dict`
- Produces: response trace field `optional_model_mode` with `requested`, `selected`, `reason`, `mode`, `model`, and `content_logged`.

- [ ] **Step 1: Write failing decision tests**

Add tests using a fake safe local provider whose `list_models()` returns capability objects with `provider_id`, `model_id`, and `metadata["size"]`:

```python
def test_optional_strong_mode_selects_only_configured_installed_model(monkeypatch):
    provider = SimpleNamespace(
        list_models=lambda: [
            SimpleNamespace(provider_id="ollama", model_id="qwen3:8b", metadata={"size": 5_200_000_000})
        ]
    )
    monkeypatch.setattr(server, "_provider_is_safe_local_candidate", lambda value: value is provider)
    monkeypatch.setattr(server.NOVA_GATEWAY.providers, "get_provider", lambda name: provider)
    monkeypatch.setattr(server.MODEL_QUALITY, "is_quarantined", lambda provider_id, model_id: False)

    decision = server._optional_strong_model_decision({"nova_model_mode": "strong"})

    assert decision["selected"] is True
    assert decision["model"] == "qwen3:8b"
    assert decision["timeout_seconds"] == 240
    assert decision["keep_alive"] == "5m"
    assert decision["content_logged"] is False


def test_optional_strong_mode_rejects_unknown_mode_and_falls_back_when_missing(monkeypatch):
    provider = SimpleNamespace(list_models=lambda: [])
    monkeypatch.setattr(server, "_provider_is_safe_local_candidate", lambda value: value is provider)
    monkeypatch.setattr(server.NOVA_GATEWAY.providers, "get_provider", lambda name: provider)

    unknown = server._optional_strong_model_decision({"nova_model_mode": "qwen3:8b"})
    missing = server._optional_strong_model_decision({"nova_model_mode": "strong"})

    assert unknown["selected"] is False
    assert unknown["reason"] == "unsupported_mode"
    assert missing["selected"] is False
    assert missing["reason"] == "model_unavailable"
```

- [ ] **Step 2: Run both tests and confirm the helper is missing**

Run: `python -m pytest tests/test_nova_enhanced_server.py -k "optional_strong_mode_selects or optional_strong_mode_rejects" -q`

Expected: FAIL because `_optional_strong_model_decision` does not exist.

- [ ] **Step 3: Implement the minimal allowlisted decision helper**

Implement `_optional_strong_model_decision` beside `_direct_middle_route_decision`. It must:

```python
mode = str((context or {}).get("nova_model_mode") or "").strip().lower()
```

- Return `ordinary_route` when the mode is empty or `nova`.
- Return `unsupported_mode` for every value except `strong`.
- Return `raw_adapter_bypass` when Strong and a raw adapter are both requested.
- Require `LocalLLMConfig().provider == "ollama"`.
- Resolve the existing local Ollama provider and require `_provider_is_safe_local_candidate(provider)`.
- Match the configured model exactly, case-insensitively, against `provider.list_models()`.
- Reject a quarantined exact match using `MODEL_QUALITY.is_quarantined("ollama", model)`.
- On success return `selected=True`, the configured model, reported size, configured timeout, configured keep-alive, tier `strong`, and `content_logged=False`.
- Catch provider/configuration errors and return a safe reason without raising into the chat transport.

- [ ] **Step 4: Run the decision tests**

Run: `python -m pytest tests/test_nova_enhanced_server.py -k "optional_strong_mode_selects or optional_strong_mode_rejects" -q`

Expected: both PASS.

- [ ] **Step 5: Write a failing routing-precedence test**

```python
def test_optional_strong_mode_overrides_middle_selection_but_keeps_nova_route(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        server,
        "_optional_strong_model_decision",
        lambda context, raw_adapter_request=False: {
            "requested": True,
            "selected": True,
            "reason": "selected",
            "mode": "strong",
            "model": "qwen3:8b",
            "estimated_model_bytes": 5_200_000_000,
            "timeout_seconds": 240,
            "keep_alive": "5m",
            "tier": "strong",
            "content_logged": False,
        },
    )
    monkeypatch.setattr(
        server,
        "_direct_middle_route_decision",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("middle route must not replace Strong")),
    )
    monkeypatch.setattr(server, "brain_route", lambda text, context=None: captured.update(context) or ("strong answer", {"local_llm_synthesis_used": True, "local_llm_model": "qwen3:8b"}))

    response, trace = server._run_nova_chat_turn("Explain emergence.", {"nova_model_mode": "strong"})

    assert response == "strong answer"
    assert captured["primary_model_override"] == "qwen3:8b"
    assert captured["primary_model_tier"] == "strong"
    assert trace["optional_model_mode"]["selected"] is True
    assert trace["answer_firewall"]["checked"] is True
```

- [ ] **Step 6: Run the precedence test and confirm Strong is not yet applied**

Run: `python -m pytest tests/test_nova_enhanced_server.py::test_optional_strong_mode_overrides_middle_selection_but_keeps_nova_route -q`

Expected: FAIL because the ordinary middle-route decision still runs or the Strong override is absent.

- [ ] **Step 7: Apply Strong before automatic middle routing**

In `_run_nova_chat_turn_impl`:

- Compute `optional_model_mode = _optional_strong_model_decision(context, raw_adapter_request=raw_adapter_request)` after raw-mode detection.
- In the model-generated branch, when selected, set `primary_model_override`, `primary_model_size_bytes`, `primary_model_timeout`, `primary_model_keep_alive`, and `primary_model_tier` from the decision.
- Use a non-selected `direct_middle_routing` trace with reason `optional_strong_mode` and do not call `_direct_middle_route_decision`.
- Emit progress stage `strong_local_model` with label `Nova Strong is using Qwen 3 8B locally.`
- When Strong is not selected, preserve the existing automatic middle route exactly.
- Add `trace["optional_model_mode"] = optional_model_mode` after `brain_route` returns so unavailable/unsupported requests remain observable.
- Do not set `raw_adapter_request`; the existing firewall and tool path must remain managed.

- [ ] **Step 8: Run focused and surrounding server tests**

Run: `python -m pytest tests/test_nova_enhanced_server.py -k "optional_strong or direct_middle or raw_adapter" -q`

Expected: all selected tests PASS.

- [ ] **Step 9: Commit the server unit**

```powershell
git add -- nova_enhanced_server.py tests/test_nova_enhanced_server.py
git commit -m "feat: route Nova Strong through qwen3 8b"
```

### Task 3: Phone and PC model selector

**Files:**
- Modify: `nova_chat_web.html`
- Test: `tests/test_nova_enhanced_server.py`

**Interfaces:**
- Consumes: request field `nova_model_mode: "strong"` from Task 2.
- Produces: browser state `managedModelMode`, selector value `strong`, and a status/progress label for Nova Strong.

- [ ] **Step 1: Write the failing browser-contract test**

```python
def test_web_ui_exposes_managed_strong_mode_without_changing_raw_modes():
    html = server.WEB_HTML

    assert '<option value="strong">Nova Strong · Qwen 3 8B</option>' in html
    assert "let managedModelMode = 'nova'" in html
    assert "payload.nova_model_mode = 'strong'" in html
    assert "Strong · Qwen 3 8B · CPU slow" in html
    assert "Nova Strong keeps identity, memory, tools, and safety" in html
    assert "trainedAdapterOnlyMode = ['qwen','dolphin'].includes(requested)" in html
    assert "Raw Qwen · no tools" in html
    assert "Raw Dolphin · no tools" in html
```

- [ ] **Step 2: Run the test and confirm the selector option is absent**

Run: `python -m pytest tests/test_nova_enhanced_server.py::test_web_ui_exposes_managed_strong_mode_without_changing_raw_modes -q`

Expected: FAIL on the missing `strong` option.

- [ ] **Step 3: Implement minimal managed-mode browser state**

In `nova_chat_web.html`:

- Add `<option value="strong">Nova Strong · Qwen 3 8B</option>` directly after Nova.
- Add `let managedModelMode = 'nova';` beside the raw-adapter booleans.
- Store and load `managedModelMode` in `ADAPTER_MODE_STORAGE_KEY`; accept only `nova` and `strong` from storage.
- Make `currentModelMode()` return raw Dolphin/Raw Qwen first, otherwise `managedModelMode`.
- In `selectModelMode`, allow `strong`; set `managedModelMode` to `strong` only for that choice; set `trainedAdapterOnlyMode = ['qwen','dolphin'].includes(requested)` and keep Dolphin detection unchanged.
- Set Strong status to `Strong · Qwen 3 8B · CPU slow`; keep the current Nova and raw status strings unchanged.
- Announce: `Nova Strong keeps identity, memory, tools, and safety while Qwen 3 8B handles model-generated answers. It may respond slowly on this CPU.`
- In `buildChatPayload`, add `payload.nova_model_mode = 'strong'` only when `managedModelMode === 'strong'` and no raw adapter is active.
- Add `strong_local_model: 'Nova Strong is using Qwen 3 8B locally'` to `streamProgressLabel`.
- Keep the selector disabled while `activeChatController` exists.

- [ ] **Step 4: Run the browser-contract and raw-mode tests**

Run: `python -m pytest tests/test_nova_enhanced_server.py -k "web_ui_exposes_managed_strong or web_ui_raw_mode" -q`

Expected: both PASS.

- [ ] **Step 5: Run the full targeted suite**

Run: `python -m pytest tests/test_nova_local_llm_config.py tests/test_nova_enhanced_server.py -q`

Expected: all tests PASS, with zero failures.

- [ ] **Step 6: Commit the browser unit**

```powershell
git add -- nova_chat_web.html tests/test_nova_enhanced_server.py
git commit -m "feat: add Nova Strong model selector"
```

### Task 4: Live verification without changing defaults

**Files:**
- No production-file changes expected.

**Interfaces:**
- Verifies: installed Ollama model, browser page contract, server health, managed Strong trace, and unchanged 3B default configuration.

- [ ] **Step 1: Verify installed and running model state**

Run:

```powershell
$ollama = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
& $ollama list | Select-String -Pattern '^qwen3:8b\s'
& $ollama ps
```

Expected: `qwen3:8b` is installed. Do not stop or unload any listed model.

- [ ] **Step 2: Restart only Nova through its existing watchdog path**

Use the repository's existing restart/health workflow rather than terminating unrelated Ollama processes. Confirm the service returns HTTP 200 at its local health endpoint and the Tailscale page returns HTTP 200.

- [ ] **Step 3: Send one bounded Strong-mode smoke request**

POST a short prompt such as `Reply with exactly: STRONG READY` using `nova_model_mode: "strong"`, the existing paired/authenticated local request path, and a client timeout of 300 seconds.

Expected: the transport remains connected, the response trace contains `optional_model_mode.selected == true`, and `local_llm_model == "qwen3:8b"`. If the response falls back, report the exact safe reason from `optional_model_mode.reason` and leave ordinary Nova available.

- [ ] **Step 4: Re-run the full targeted tests after the live request**

Run: `python -m pytest tests/test_nova_local_llm_config.py tests/test_nova_enhanced_server.py -q`

Expected: all tests PASS with zero failures.

- [ ] **Step 5: Verify defaults and remote page one final time**

Run:

```powershell
Select-String -Path .nova_llm_config -Pattern '^NOVA_DEEP_LOCAL_LLM_MODEL=qwen2.5:3b$','^NOVA_ACTIVE_BRAIN=qwen2.5:3b$','^NOVA_OPTIONAL_STRONG_MODEL=qwen3:8b$'
```

Expected: all three lines are present. Confirm the remote page still returns HTTP 200 and its HTML contains `Nova Strong · Qwen 3 8B`.
