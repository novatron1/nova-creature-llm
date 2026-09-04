# Nova Tailscale Remote Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Nova reliably usable on its Windows host and from a paired phone anywhere through a stable, private Tailscale Serve HTTPS address whenever the PC is on.

**Architecture:** Nova continues listening only on `127.0.0.1:3000`. A focused Tailscale manager configures a private Serve mapping on HTTPS port `8443`, leaving the PC's existing port-443 Serve/Funnel configuration untouched; a shared proxy-identity boundary ensures Tailscale-proxied requests are remote and require Nova pairing. The existing Foundation/Desktop APIs and PWA surface expose safe status, pairing, copy, enable, disable, and recovery flows.

**Tech Stack:** Python 3.10+, standard-library HTTP server, subprocess JSON integration with Tailscale CLI 1.52+, HTML/CSS/vanilla JavaScript PWA, pytest/unittest, Windows batch launcher.

## Global Constraints

- Nova's local server remains bound to `127.0.0.1:3000` by default.
- Nova's private Tailscale HTTPS endpoint uses port `8443`; do not alter, reset, disable, or reuse the PC's existing port-443 Serve/Funnel mapping.
- Do not use Tailscale Funnel, Cloudflare Quick Tunnel, router port forwarding, wildcard CORS, or a public hostname for Nova.
- Tailscale identity headers are trusted only when the direct TCP peer is loopback and `NOVA_TRUST_TAILSCALE_SERVE=true`.
- A trusted Tailscale request is classified as remote and still requires a valid Nova paired-device token.
- Never expose Ollama, ComfyUI, shell, filesystem, training, or other internal service ports.
- Remote status payloads contain no Tailscale account identity, email, node keys, authorization material, prompts, answers, or memory content.
- Existing local-only startup and localhost no-auth behavior must remain unchanged.
- The existing worktree has extensive user-owned modifications in files this feature must touch. Do not stage or commit a pre-existing modification. The commit commands below are valid only in a clean isolated checkout with the approved current app state as its baseline; in this checkout, record each checkpoint with scoped test output and `git diff --check` instead.
- Follow TDD for every behavior change: failing test, observed failure, minimal implementation, passing test.

---

## File Structure

### Create

- `src/nova_proxy_identity.py` — one privacy-safe trust decision for proxied client identity.
- `src/nova_tailscale.py` — Tailscale discovery, sanitized status parsing, conflict detection, and owned Serve enable/disable operations.
- `tools/nova_anywhere.py` — one-process Windows launch orchestration for Tailscale setup, Nova startup, health wait, browser opening, and shutdown.
- `START_NOVA_ANYWHERE_WINDOWS.bat` — double-click entry point that selects Python, installs the existing bounded runtime requirements, and invokes the orchestrator.
- `tests/test_nova_proxy_identity.py` — isolated trusted-proxy boundary tests.
- `tests/test_nova_tailscale.py` — deterministic Tailscale CLI parsing and mutation tests with a fake runner.
- `tests/test_nova_anywhere.py` — launcher orchestration tests with fake process, health, and browser dependencies.

### Modify

- `src/nova_gateway/config.py` — add the explicit `trust_tailscale_serve` policy field.
- `src/nova_gateway/http.py` — apply the shared Tailscale proxy identity before Cloudflare/generic proxy handling.
- `src/nova_foundation_http.py` — apply the shared identity, use a privacy-safe rate-limit key, and prefer the verified private phone URL for pairing QR codes.
- `src/nova_desktop.py` — include sanitized remote-access status and guarded local enable/disable operations.
- `src/nova_desktop_http.py` — add the local-only remote-access mutation endpoint.
- `nova_enhanced_server.py` — construct and wire one Tailscale manager, update its Nova port at startup, and print private readiness without exposing secrets.
- `nova_chat_web.html` — add the remote-phone status, private URL, and desktop-only controls to the existing Foundation card.
- `assets/nova_foundation_ui.js` — load, render, copy, enable, and disable remote access with clear phone recovery copy.
- `assets/nova_foundation_ui.css` — responsive private-URL and status presentation.
- `service-worker.js` — bump the shell cache version so installed phones receive the updated UI.
- `offline.html` — explain PC-offline versus Tailscale-disconnected recovery.
- `tests/test_nova_foundation.py` — Tailscale pairing enforcement and private QR URL integration.
- `tests/test_nova_gateway_http.py` — native gateway behavior through the trusted Tailscale proxy.
- `tests/test_nova_desktop_experience.py` — local-only status/mutation API and UI wiring.
- `tests/test_windows_launcher.py` — verify the new launcher uses the orchestrator without changing the standard launcher.
- `QUICK_START_LAPTOP.txt` — distinguish local and Anywhere launch paths.
- `QUICK_START_PHONE_CONNECT.txt` — replace same-Wi-Fi-only instructions with the private Anywhere flow while retaining LAN fallback documentation.
- `README_LAPTOP_INSTALL.md` — full Tailscale setup, security, restart, and troubleshooting guidance.
- `docs/NOVA_GATEWAY_CONNECTION_GUIDE.md` — document private Tailscale Serve access and explicitly reject Funnel for Nova.
- `docs/NOVA_GATEWAY_SECURITY_COST_BACKUP.md` — record the trusted-proxy boundary and no-public-fallback policy.

---

### Task 1: Trusted Tailscale Proxy Identity Boundary

**Files:**
- Create: `src/nova_proxy_identity.py`
- Create: `tests/test_nova_proxy_identity.py`
- Modify: `src/nova_gateway/config.py:46-180`
- Modify: `src/nova_gateway/http.py:81-104`
- Modify: `src/nova_foundation_http.py:202-240`
- Test: `tests/test_nova_foundation.py:318-365`
- Test: `tests/test_nova_gateway_http.py`

**Interfaces:**
- Consumes: an HTTP handler exposing `client_address` and case-insensitive `headers`.
- Produces: `trusted_tailscale_client_key(handler: Any, *, enabled: bool | None = None, env: Mapping[str, str] | None = None) -> str | None`.
- Produces: `GatewayConfig.trust_tailscale_serve: bool` loaded from `NOVA_TRUST_TAILSCALE_SERVE`, default `False`.
- Contract: the returned key is `tailscale:` plus 24 hexadecimal characters derived from the login header; raw identity never leaves the function.

- [ ] **Step 1: Write the proxy-boundary unit tests**

```python
from email.message import Message
from types import SimpleNamespace

from nova_proxy_identity import trusted_tailscale_client_key


def handler(peer: str, login: str = "phone@example.test"):
    headers = Message()
    headers["Tailscale-User-Login"] = login
    return SimpleNamespace(client_address=(peer, 41000), headers=headers)


def test_trusted_tailscale_identity_requires_explicit_policy_and_loopback():
    assert trusted_tailscale_client_key(handler("127.0.0.1"), enabled=False) is None
    assert trusted_tailscale_client_key(handler("192.0.2.44"), enabled=True) is None


def test_trusted_tailscale_identity_is_opaque_and_stable():
    first = trusted_tailscale_client_key(handler("127.0.0.1"), enabled=True)
    second = trusted_tailscale_client_key(handler("::1"), enabled=True)
    assert first == second
    assert first is not None and first.startswith("tailscale:")
    assert "phone@example.test" not in first
    assert len(first) == len("tailscale:") + 24


def test_trusted_tailscale_identity_rejects_control_characters():
    assert trusted_tailscale_client_key(
        handler("127.0.0.1", "phone@example.test\nspoofed"), enabled=True
    ) is None
```

- [ ] **Step 2: Run the new unit tests and observe the missing-module failure**

Run: `py -3 -m pytest tests/test_nova_proxy_identity.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'nova_proxy_identity'`.

- [ ] **Step 3: Implement the privacy-safe helper**

```python
"""Trusted reverse-proxy identity helpers with privacy-safe client keys."""

from __future__ import annotations

import hashlib
import ipaddress
import os
from typing import Any, Mapping


_TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}


def trusted_tailscale_client_key(
    handler: Any,
    *,
    enabled: bool | None = None,
    env: Mapping[str, str] | None = None,
) -> str | None:
    source = os.environ if env is None else env
    allowed = (
        str(source.get("NOVA_TRUST_TAILSCALE_SERVE", "false")).strip().lower()
        in _TRUE_VALUES
        if enabled is None
        else bool(enabled)
    )
    if not allowed:
        return None
    direct = str((getattr(handler, "client_address", None) or ("",))[0]).split("%", 1)[0]
    try:
        if not ipaddress.ip_address(direct).is_loopback:
            return None
    except ValueError:
        return None
    headers = getattr(handler, "headers", {})
    login = str(headers.get("Tailscale-User-Login") or "").strip()
    if not login or len(login) > 320 or any(ord(character) < 32 for character in login):
        return None
    digest = hashlib.sha256(login.encode("utf-8")).hexdigest()[:24]
    return "tailscale:" + digest


__all__ = ["trusted_tailscale_client_key"]
```

- [ ] **Step 4: Run the helper tests and verify they pass**

Run: `py -3 -m pytest tests/test_nova_proxy_identity.py -q`

Expected: `3 passed`.

- [ ] **Step 5: Add failing Foundation and gateway integration cases**

Add a Foundation assertion that a loopback peer carrying `Tailscale-User-Login` remains local when the policy is absent, becomes nonlocal when the policy is enabled, receives a `tailscale:` client key, and gets `401 pairing_required` without a device token. Add the same classification case to `tests/test_nova_gateway_http.py` using `GatewayConfig(trust_tailscale_serve=True, enable_remote_access=True, rate_limit_enabled=False)`.

```python
def test_tailscale_loopback_proxy_is_remote_only_when_explicitly_trusted(monkeypatch):
    handler = object.__new__(server.NovaHandler)
    handler.client_address = ("127.0.0.1", 41000)
    handler.headers = Message()
    handler.headers["Tailscale-User-Login"] = "phone@example.test"

    monkeypatch.delenv("NOVA_TRUST_TAILSCALE_SERVE", raising=False)
    assert handler._client_is_local() is True

    monkeypatch.setenv("NOVA_TRUST_TAILSCALE_SERVE", "true")
    assert handler._client_is_local() is False
    assert server.FOUNDATION_HTTP.client_ip(handler).startswith("tailscale:")
```

- [ ] **Step 6: Wire the helper through both HTTP boundaries**

Add `trust_tailscale_serve: bool = False` to `GatewayConfig`, load it with `_bool(source, "NOVA_TRUST_TAILSCALE_SERVE", False)`, and include only its boolean value in `public_dict()`. In both client-key functions, check Tailscale before Cloudflare or generic forwarded headers:

```python
tailscale = trusted_tailscale_client_key(
    handler,
    enabled=self.config.trust_tailscale_serve,
)
if tailscale:
    return tailscale
```

Foundation uses `trusted_tailscale_client_key(handler)` and otherwise preserves its current Cloudflare and `NOVA_TRUST_PROXY_HEADERS` behavior. Because `tailscale:<digest>` is not an IP address, the existing local-address checks classify it as remote and generic API-key IP restrictions fail closed.

- [ ] **Step 7: Run the scoped security tests**

Run: `py -3 -m pytest tests/test_nova_proxy_identity.py tests/test_nova_foundation.py tests/test_nova_gateway_http.py -q`

Expected: all selected tests pass; existing Cloudflare cases remain green.

- [ ] **Step 8: Checkpoint the task**

Run: `git diff --check -- src/nova_proxy_identity.py src/nova_gateway/config.py src/nova_gateway/http.py src/nova_foundation_http.py tests/test_nova_proxy_identity.py tests/test_nova_foundation.py tests/test_nova_gateway_http.py`

Expected: no whitespace errors. In a clean isolated checkout only, commit with `git commit -m "feat: classify Tailscale Serve clients as remote"` after staging exactly those files. In the current dirty checkout, do not stage them.

---

### Task 2: Safe Tailscale Serve Manager

**Files:**
- Create: `src/nova_tailscale.py`
- Create: `tests/test_nova_tailscale.py`

**Interfaces:**
- Consumes: the Tailscale CLI commands `status --json`, `serve status --json`, `serve --bg --yes --https=8443 http://127.0.0.1:3000`, and `serve --https=8443 off`.
- Produces: `TailscaleError(RuntimeError)`.
- Produces: `NovaTailscaleManager(nova_port: int = 3000, https_port: int = 8443, *, executable: str | Path | None = None, command_runner: Callable | None = None)`.
- Produces: `status() -> dict[str, Any]`, `enable() -> dict[str, Any]`, `disable() -> dict[str, Any]`, and `set_nova_port(port: int) -> None`.
- Status keys: `ok`, `installed`, `connected`, `backend_state`, `serve_enabled`, `serve_conflict`, `private_url`, `nova_port`, `https_port`, `reason`, and `message`.

- [ ] **Step 1: Write deterministic status, enable, conflict, and disable tests**

```python
class FakeRunner:
    def __init__(self, *, conflict: bool = False):
        self.calls: list[list[str]] = []
        self.enabled = False
        self.conflict = conflict

    def __call__(self, arguments: list[str], timeout: float):
        self.calls.append(list(arguments))
        if arguments[1:] == ["status", "--json"]:
            payload = {
                "BackendState": "Running",
                "Self": {
                    "Online": True,
                    "DNSName": "nova-host.example.ts.net.",
                },
            }
        elif arguments[1:] == ["serve", "status", "--json"]:
            handlers = {}
            if self.enabled or self.conflict:
                handlers = {
                    "nova-host.example.ts.net:8443": {
                        "Handlers": {
                            "/": {
                                "Proxy": (
                                    "http://127.0.0.1:9090"
                                    if self.conflict
                                    else "http://127.0.0.1:3000"
                                )
                            }
                        }
                    }
                }
            payload = {"Web": handlers, "AllowFunnel": {}}
        elif arguments[1:3] == ["serve", "--bg"]:
            self.enabled = True
            payload = {}
        elif arguments[1:] == ["serve", "--https=8443", "off"]:
            self.enabled = False
            payload = {}
        else:
            return subprocess.CompletedProcess(arguments, 1, "", "unexpected command")
        return subprocess.CompletedProcess(arguments, 0, json.dumps(payload), "")


@pytest.fixture
def fake_runner():
    return FakeRunner()


@pytest.fixture
def conflicting_runner():
    return FakeRunner(conflict=True)


def test_status_reports_private_url_without_leaking_account(fake_runner):
    manager = NovaTailscaleManager(
        nova_port=3000,
        https_port=8443,
        executable="tailscale",
        command_runner=fake_runner,
    )
    status = manager.status()
    assert status["connected"] is True
    assert status["private_url"] == "https://nova-host.example.ts.net:8443"
    assert status["serve_enabled"] is False
    assert "LoginName" not in json.dumps(status)


def test_enable_uses_private_8443_and_confirms_postcondition(fake_runner):
    manager = NovaTailscaleManager(
        nova_port=3000,
        https_port=8443,
        executable="tailscale",
        command_runner=fake_runner,
    )
    enabled = manager.enable()
    assert enabled["serve_enabled"] is True
    assert [
        "tailscale", "serve", "--bg", "--yes", "--https=8443",
        "http://127.0.0.1:3000",
    ] in fake_runner.calls


def test_enable_refuses_to_replace_an_existing_8443_handler(conflicting_runner):
    manager = NovaTailscaleManager(
        nova_port=3000,
        https_port=8443,
        executable="tailscale",
        command_runner=conflicting_runner,
    )
    with pytest.raises(TailscaleError, match="8443"):
        manager.enable()


def test_disable_refuses_unowned_mapping_and_removes_owned_mapping(fake_runner):
    manager = NovaTailscaleManager(
        nova_port=3000,
        https_port=8443,
        executable="tailscale",
        command_runner=fake_runner,
    )
    manager.enable()
    disabled = manager.disable()
    assert disabled["serve_enabled"] is False
    assert ["tailscale", "serve", "--https=8443", "off"] in fake_runner.calls
```

The fake runner returns a connected `status --json` payload whose DNS name ends with a dot, starts with an empty `serve status --json` payload, records every argument list, and updates only its synthetic port-8443 mapping after an enable/disable command.

- [ ] **Step 2: Run the manager tests and observe the missing-module failure**

Run: `py -3 -m pytest tests/test_nova_tailscale.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'nova_tailscale'`.

- [ ] **Step 3: Implement executable discovery and bounded JSON commands**

Use `shutil.which("tailscale")`, then Windows candidates under `ProgramFiles` and `LOCALAPPDATA`. Run commands without `shell=True`, with `capture_output=True`, `text=True`, `encoding="utf-8"`, `errors="replace"`, and a 10-second timeout. Convert nonzero exits, invalid JSON, and timeouts to fixed `reason` values and bounded messages; never return raw command output.

```python
def _default_runner(arguments: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
```

- [ ] **Step 4: Implement sanitized status parsing and ownership checks**

Normalize `Self.DNSName` by removing its final dot. Build the service key as `<dns>:<https_port>` and the expected proxy as `http://127.0.0.1:<nova_port>`. A mapping is owned only when `Web[key].Handlers["/"].Proxy` equals that expected proxy and `AllowFunnel[key]` is not true.

```python
service_key = f"{dns_name}:{self.https_port}"
web_entry = (serve_payload.get("Web") or {}).get(service_key) or {}
handler = (web_entry.get("Handlers") or {}).get("/") or {}
actual_proxy = str(handler.get("Proxy") or "").rstrip("/")
expected_proxy = f"http://127.0.0.1:{self.nova_port}"
funnel_enabled = bool((serve_payload.get("AllowFunnel") or {}).get(service_key))
owned = actual_proxy == expected_proxy and not funnel_enabled
conflict = bool(actual_proxy and actual_proxy != expected_proxy) or funnel_enabled
```

- [ ] **Step 5: Implement fail-closed enable and owned-only disable**

`enable()` requires `installed`, `connected`, and no conflict, runs the exact private Serve command, then calls `status()` again and raises `TailscaleError` unless `serve_enabled` is true and `serve_conflict` is false. `disable()` returns the current status when nothing is configured, raises for an unowned mapping, runs the exact `off` command for an owned mapping, and verifies it disappeared.

- [ ] **Step 6: Run the manager tests**

Run: `py -3 -m pytest tests/test_nova_tailscale.py -q`

Expected: all manager cases pass without invoking the real Tailscale CLI.

- [ ] **Step 7: Checkpoint the task**

Run: `git diff --check -- src/nova_tailscale.py tests/test_nova_tailscale.py`

Expected: no whitespace errors. In a clean isolated checkout only, commit with `git add src/nova_tailscale.py tests/test_nova_tailscale.py && git commit -m "feat: manage private Tailscale Serve access"`. In the current dirty checkout, leave the new files unstaged until the user decides how to integrate the broader dirty worktree.

---

### Task 3: Server, Pairing, and Local Management Integration

**Files:**
- Modify: `src/nova_foundation_http.py:174-186,351-387,500-527`
- Modify: `src/nova_desktop.py:20-122`
- Modify: `src/nova_desktop_http.py:23-49`
- Modify: `nova_enhanced_server.py:175-200,14234-14282`
- Test: `tests/test_nova_foundation.py`
- Test: `tests/test_nova_desktop_experience.py`

**Interfaces:**
- Consumes: `NovaTailscaleManager.status/enable/disable/set_nova_port` from Task 2.
- Produces: `NovaDesktopManager(application_root: str | Path, port: int = 3000, *, startup_directory: str | Path | None = None, platform_name: str | None = None, remote_access_manager: NovaTailscaleManager | None = None)`.
- Produces: `NovaDesktopManager.set_remote_access(enabled: bool) -> dict[str, Any]`.
- Produces: local-only `POST /api/desktop/remote-access` with body `{"enabled": true|false}`.
- Produces: `FoundationHttpController(foundation_provider: Callable[[], NovaFoundation], application_root: str | Path, remote_phone_url_provider: Callable[[], str | None] | None = None)`.

- [ ] **Step 1: Write failing local-management API tests**

Extend `test_desktop_vault_and_pwa_http_endpoints` with a fake manager that records `enable()` and `disable()` calls and returns a sanitized status. Assert `/api/desktop/status` contains the nested `remote_access` object and both mutations work locally.

```python
class FakeRemoteAccess:
    def __init__(self):
        self.enabled = False

    def status(self):
        return {
            "ok": True,
            "installed": True,
            "connected": True,
            "serve_enabled": self.enabled,
            "serve_conflict": False,
            "private_url": "https://nova-host.example.ts.net:8443",
            "reason": "ready" if self.enabled else "serve_not_configured",
        }

    def enable(self):
        self.enabled = True
        return self.status()

    def disable(self):
        self.enabled = False
        return self.status()
```

Also create a nonloopback handler case and assert `POST /api/desktop/remote-access` returns `403 local_management_required` without calling the fake manager.

- [ ] **Step 2: Write failing private pairing-URL tests**

Construct `FoundationHttpController` with `remote_phone_url_provider=lambda: "https://nova-host.example.ts.net:8443"`, bind the test HTTP server to loopback, create a pairing session locally, and assert:

```python
assert created["phone_url"] == "https://nova-host.example.ts.net:8443"
assert created["pairing_url"].startswith(
    "https://nova-host.example.ts.net:8443/?pair="
)
assert created["connection_kind"] == "tailscale"
assert created["lan_accessible"] is True
```

- [ ] **Step 3: Run the integration tests and observe failures**

Run: `py -3 -m pytest tests/test_nova_foundation.py tests/test_nova_desktop_experience.py -q`

Expected: failures show the missing constructor arguments, remote status field, remote mutation route, and Tailscale pairing URL.

- [ ] **Step 4: Add manager composition to the desktop boundary**

Store the optional manager on `NovaDesktopManager`. `status()` adds `remote_access` from the manager or a fixed unsupported result. `set_remote_access()` raises `DesktopError` when no manager exists and delegates only a boolean choice.

```python
def set_remote_access(self, enabled: bool) -> dict[str, Any]:
    if self.remote_access_manager is None:
        raise DesktopError("Private phone access is unavailable on this system.")
    return (
        self.remote_access_manager.enable()
        if enabled
        else self.remote_access_manager.disable()
    )
```

Update `DesktopHttpController.handle_post()` to recognize both `/api/desktop/autostart` and `/api/desktop/remote-access`, run the existing local-management guard first, validate `enabled` as an actual boolean, and return bounded `DesktopError`, `TailscaleError`, `OSError`, and `ValueError` messages as status 400.

- [ ] **Step 5: Prefer the verified private URL for pairing**

Add `_remote_phone_url()` that accepts only `https`, no username/password/query/fragment, and a hostname ending in `.ts.net`. At the start of `_phone_base_url()`, return `(remote_url, True, "tailscale")` when valid. Preserve the existing LAN path as `(url, True, "lan")` and unavailable path as `(None, False, "unavailable")`. Add `connection_kind` to the pairing response while retaining `lan_accessible` for compatibility.

- [ ] **Step 6: Wire one manager into the live server**

Instantiate one global manager before the HTTP controllers:

```python
TAILSCALE = NovaTailscaleManager(
    nova_port=3000,
    https_port=int(os.environ.get("NOVA_TAILSCALE_HTTPS_PORT", "8443")),
)
FOUNDATION_HTTP = FoundationHttpController(
    lambda: FOUNDATION,
    ROOT,
    remote_phone_url_provider=lambda: TAILSCALE.status().get("private_url")
    if TAILSCALE.status().get("serve_enabled")
    else None,
)
DESKTOP = NovaDesktopManager(ROOT, port=3000, remote_access_manager=TAILSCALE)
```

Avoid calling `TAILSCALE.status()` twice by replacing the inline lambda with a small `_active_tailscale_url()` function that stores one result locally. In `main()`, call both `DESKTOP.port = port` and `TAILSCALE.set_nova_port(port)` before binding. When trusted Serve mode is enabled, print only the sanitized private URL and readiness reason.

- [ ] **Step 7: Run the integration tests**

Run: `py -3 -m pytest tests/test_nova_foundation.py tests/test_nova_desktop_experience.py tests/test_nova_enhanced_server.py -q`

Expected: selected Foundation/Desktop/server tests pass, including existing LAN QR and Cloudflare tunnel behavior.

- [ ] **Step 8: Checkpoint the task**

Run: `git diff --check -- src/nova_foundation_http.py src/nova_desktop.py src/nova_desktop_http.py nova_enhanced_server.py tests/test_nova_foundation.py tests/test_nova_desktop_experience.py`

Expected: no whitespace errors. In a clean isolated checkout only, commit with `git commit -m "feat: expose private phone access controls"` after staging exactly the listed files. In the current dirty checkout, do not stage them.

---

### Task 4: Desktop Settings and Phone PWA Experience

**Files:**
- Modify: `nova_chat_web.html:1171-1188`
- Modify: `assets/nova_foundation_ui.js:674-734,851-876`
- Modify: `assets/nova_foundation_ui.css`
- Modify: `service-worker.js:1`
- Modify: `offline.html`
- Test: `tests/test_nova_desktop_experience.py:219-235`
- Test: `tests/test_nova_foundation.py:382-430`

**Interfaces:**
- Consumes: `GET /api/desktop/status` with nested `remote_access` and local-only `POST /api/desktop/remote-access` from Task 3.
- Produces: `renderNovaRemoteAccess(remote: object)`, `copyNovaPhoneUrl()`, and `toggleNovaRemoteAccess()` browser functions.
- Produces: DOM IDs `novaRemoteAccessState`, `novaRemotePhoneUrl`, `copyNovaPhoneUrlBtn`, and `toggleNovaRemoteAccessBtn`.

- [ ] **Step 1: Add failing UI contract assertions**

```python
assert 'id="novaRemoteAccessState"' in html
assert 'id="novaRemotePhoneUrl"' in html
assert 'id="copyNovaPhoneUrlBtn"' in html
assert 'id="toggleNovaRemoteAccessBtn"' in html
assert "/api/desktop/remote-access" in script
assert "renderNovaRemoteAccess" in script
assert "copyNovaPhoneUrl" in script
assert "NOVA_TRUST_TAILSCALE_SERVE" not in html
assert "tailcd" not in html.lower()
assert "nova-shell-2026-08-16-tailscale-v1" in worker
```

- [ ] **Step 2: Run the UI contract tests and observe failure**

Run: `py -3 -m pytest tests/test_nova_desktop_experience.py::test_pwa_manifest_and_owner_controls_are_wired tests/test_nova_foundation.py::test_foundation_controls_are_present_in_ui -q`

Expected: assertions fail for the new IDs, functions, endpoint, and cache name.

- [ ] **Step 3: Add the private phone status and controls to the existing card**

Add two rows beneath Start with Windows: a private-access state and a link whose text is populated at runtime. Add Copy Link and Enable/Disable Remote Phone buttons; keep the mutation button hidden unless `localManagementAvailable` is true.

```html
<div class="status-row"><strong>Remote phone</strong><span id="novaRemoteAccessState">Checking...</span></div>
<div class="status-row remote-phone-row"><strong>Private address</strong><a id="novaRemotePhoneUrl" hidden rel="noopener"></a></div>
<button class="panel-action" id="copyNovaPhoneUrlBtn" onclick="copyNovaPhoneUrl()" hidden>Copy Phone Link</button>
<button class="panel-action" id="toggleNovaRemoteAccessBtn" onclick="toggleNovaRemoteAccess()" hidden>Enable Remote Phone</button>
```

- [ ] **Step 4: Implement safe rendering, copy, and local mutation behavior**

`renderNovaRemoteAccess` must use `textContent`, assign `href` only after `new URL(value)` confirms `https:` and a `.ts.net` hostname, and never render raw errors. Map fixed reason codes to plain language:

```javascript
const remoteMessages = {
  ready: 'Private phone access is ready.',
  tailscale_not_installed: 'Install Tailscale on this PC to use Nova away from Wi-Fi.',
  tailscale_disconnected: 'Open Tailscale on this PC and sign in.',
  serve_not_configured: 'Tailscale is ready; enable Nova remote phone access.',
  https_port_in_use: 'Private port 8443 is already used by another Tailscale service.',
  command_failed: 'Tailscale could not update the private connection.'
};
```

`copyNovaPhoneUrl()` uses `navigator.clipboard.writeText` and falls back to selecting the link text with a temporary textarea. `toggleNovaRemoteAccess()` confirms the change, posts `{enabled}`, rerenders the returned status, and does not clear device tokens or change pairing scopes.

- [ ] **Step 5: Update installed-app and offline behavior**

Bump `CACHE_NAME` to `nova-shell-2026-08-16-tailscale-v1`. Keep private runtime/API paths uncached. Update `offline.html` to say: keep the PC awake, confirm Nova is running, and confirm Tailscale is connected on both devices; do not mention a public tunnel.

- [ ] **Step 6: Add responsive styles**

```css
.remote-phone-row{align-items:flex-start}
.remote-phone-row a{max-width:68%;color:#9fdcff;font-size:11px;text-align:right;overflow-wrap:anywhere}
@media(max-width:640px){.remote-phone-row{display:grid;gap:5px}.remote-phone-row a{max-width:100%;text-align:left}}
```

- [ ] **Step 7: Run UI and PWA tests**

Run: `py -3 -m pytest tests/test_nova_desktop_experience.py tests/test_nova_foundation.py tests/test_nova_companion_routes.py tests/test_nova_enhanced_server.py -q`

Expected: all selected tests pass; service-worker privacy assertions remain green.

- [ ] **Step 8: Checkpoint the task**

Run: `git diff --check -- nova_chat_web.html assets/nova_foundation_ui.js assets/nova_foundation_ui.css service-worker.js offline.html tests/test_nova_desktop_experience.py tests/test_nova_foundation.py`

Expected: no whitespace errors. In a clean isolated checkout only, commit with `git commit -m "feat: add private remote phone controls"` after staging exactly the listed files. In the current dirty checkout, do not stage them.

---

### Task 5: One-Click Windows Anywhere Launcher and Documentation

**Files:**
- Create: `tools/nova_anywhere.py`
- Create: `START_NOVA_ANYWHERE_WINDOWS.bat`
- Create: `tests/test_nova_anywhere.py`
- Modify: `tests/test_windows_launcher.py`
- Modify: `QUICK_START_LAPTOP.txt`
- Modify: `QUICK_START_PHONE_CONNECT.txt`
- Modify: `README_LAPTOP_INSTALL.md`
- Modify: `docs/NOVA_GATEWAY_CONNECTION_GUIDE.md`
- Modify: `docs/NOVA_GATEWAY_SECURITY_COST_BACKUP.md`

**Interfaces:**
- Consumes: `NovaTailscaleManager.enable()` from Task 2 and `nova_enhanced_server.py <port>`.
- Produces: `wait_for_nova(url: str, process: subprocess.Popen, *, timeout_seconds: float = 180.0, opener=urllib.request.urlopen, sleeper=time.sleep) -> bool`.
- Produces: `run_anywhere(root: Path, port: int, https_port: int, *, manager_factory=NovaTailscaleManager, popen_factory=subprocess.Popen, browser_open=webbrowser.open, health_opener=urllib.request.urlopen, sleeper=time.sleep) -> int`.
- Produces: a double-clickable `START_NOVA_ANYWHERE_WINDOWS.bat` that selects Python exactly as the standard launcher does and calls the Python orchestrator.

- [ ] **Step 1: Write failing orchestration tests**

Use fakes whose manager returns `https://nova-host.example.ts.net:8443`, whose process remains running until `wait()`, whose health opener succeeds, and whose browser recorder accepts one URL.

```python
def test_run_anywhere_enables_private_serve_and_starts_loopback_nova(tmp_path):
    result = run_anywhere(
        tmp_path,
        3000,
        8443,
        manager_factory=FakeManager,
        popen_factory=fake_popen,
        browser_open=opened_urls.append,
        health_opener=successful_health,
        sleeper=lambda _: None,
    )
    assert result == 0
    assert fake_popen.arguments == [sys.executable, "nova_enhanced_server.py", "3000"]
    assert fake_popen.environment["NOVA_TRUST_TAILSCALE_SERVE"] == "true"
    assert fake_popen.environment["NOVA_HOST"] == "127.0.0.1"
    assert opened_urls == ["http://127.0.0.1:3000/classic?panel=settings"]


def test_run_anywhere_does_not_start_nova_when_tailscale_enable_fails(tmp_path):
    with pytest.raises(TailscaleError, match="private connection"):
        run_anywhere(
            tmp_path,
            3000,
            8443,
            manager_factory=FailingManager,
            popen_factory=fake_popen,
        )
    assert fake_popen.calls == 0
```

- [ ] **Step 2: Add failing batch-launcher assertions**

```python
ANYWHERE_LAUNCHER = REPO_ROOT / "START_NOVA_ANYWHERE_WINDOWS.bat"


def test_anywhere_launcher_uses_bounded_python_orchestrator():
    script = ANYWHERE_LAUNCHER.read_text(encoding="utf-8")
    assert "tools\\nova_anywhere.py --port 3000 --https-port 8443" in script
    assert "NOVA_HOST=0.0.0.0" not in script
    assert "cloudflared" not in script.lower()
    assert "funnel" not in script.lower()
```

- [ ] **Step 3: Run launcher tests and observe failures**

Run: `py -3 -m pytest tests/test_nova_anywhere.py tests/test_windows_launcher.py -q`

Expected: missing module/file failures for the Anywhere orchestrator and batch launcher.

- [ ] **Step 4: Implement the orchestration helper**

`run_anywhere` validates `root/nova_enhanced_server.py`, enables the private mapping before starting Nova, sets an explicit loopback host and trust flag in the child environment, waits up to 180 seconds for `/healthz`, opens local Settings, prints the sanitized phone URL, and returns the child exit code. If health never arrives or the child exits, terminate only the child process started by this invocation and return a nonzero code. Do not disable the owned Serve mapping on normal exit because `--bg` persistence supplies the stable restart behavior.

```python
child_env = dict(os.environ)
child_env.update({
    "NOVA_HOST": "127.0.0.1",
    "NOVA_TRUST_TAILSCALE_SERVE": "true",
    "NOVA_TAILSCALE_HTTPS_PORT": str(https_port),
})
process = popen_factory(
    [sys.executable, "nova_enhanced_server.py", str(port)],
    cwd=str(root),
    env=child_env,
)
```

- [ ] **Step 5: Implement the double-click batch entry point**

Reuse the standard launcher's Python 3.10 detection and `requirements-runtime.txt` installation checks. Resolve the repository using `%~dp0`, quote every path, and finish with:

```bat
%PYTHON% "%~dp0tools\nova_anywhere.py" --root "%~dp0" --port 3000 --https-port 8443
if %errorlevel% neq 0 (
    echo [ERROR] Nova Anywhere did not start. Read the message above, then try again.
    pause
    exit /b 1
)
```

- [ ] **Step 6: Update setup and security documentation with exact daily flow**

Document these exact actions:

1. Double-click `START_NOVA_ANYWHERE_WINDOWS.bat`.
2. Confirm the launcher reports private phone access on an `https://<device>.<tailnet>.ts.net:8443` address.
3. Open Tailscale on the phone and sign into the same private network.
4. In local Nova Settings, create a one-time pairing QR code.
5. Scan, name, and pair the phone.
6. Install Nova with Add to Home Screen.
7. Keep the PC awake, Nova running, and Tailscale connected during remote use.

State that the standard launcher remains local-only, port 8443 is private Serve, port 443 is preserved, Funnel is not used for Nova, the phone cannot work while the PC is off, and no router or Ollama port should be exposed.

- [ ] **Step 7: Run launcher and documentation contract tests**

Run: `py -3 -m pytest tests/test_nova_anywhere.py tests/test_windows_launcher.py tests/test_nova_desktop_experience.py tests/test_nova_foundation.py -q`

Expected: all selected tests pass.

- [ ] **Step 8: Checkpoint the task**

Run: `git diff --check -- tools/nova_anywhere.py START_NOVA_ANYWHERE_WINDOWS.bat tests/test_nova_anywhere.py tests/test_windows_launcher.py QUICK_START_LAPTOP.txt QUICK_START_PHONE_CONNECT.txt README_LAPTOP_INSTALL.md docs/NOVA_GATEWAY_CONNECTION_GUIDE.md docs/NOVA_GATEWAY_SECURITY_COST_BACKUP.md`

Expected: no whitespace errors. In a clean isolated checkout only, commit with `git commit -m "feat: add one-click Nova Anywhere launcher"` after staging exactly the listed files. In the current dirty checkout, do not stage them.

---

### Task 6: Full Verification and Live Private-Route Proof

**Files:**
- Verify: all files listed above
- Record: `reports/nova_tailscale_remote_access_verification.json`

**Interfaces:**
- Consumes: the completed launcher, private status, pairing, gateway, and PWA behavior.
- Produces: a content-free verification report with command, exit code, duration, status, and fixed reason codes; it contains no account identity, phone name, DNS hostname, device tokens, pairing code, prompts, answers, or memory.

- [ ] **Step 1: Run the focused feature suite**

Run:

```powershell
py -3 -m pytest `
  tests/test_nova_proxy_identity.py `
  tests/test_nova_tailscale.py `
  tests/test_nova_anywhere.py `
  tests/test_nova_foundation.py `
  tests/test_nova_gateway_http.py `
  tests/test_nova_desktop_experience.py `
  tests/test_nova_companion_routes.py `
  tests/test_windows_launcher.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run server regression coverage**

Run: `py -3 -m pytest tests/test_nova_enhanced_server.py -q`

Expected: all server tests pass; no local, LAN, Cloudflare, mobile layout, streaming, or PWA regression.

- [ ] **Step 3: Run repository release checks appropriate to the changed server surface**

Run: `py -3 tools/nova_smoke_check.py`

Then run: `py -3 -m pytest -q`

Expected: smoke check passes and the full suite exits zero. If the full suite contains a pre-existing unrelated failure, capture the exact failing test and prove it also fails without the feature delta before classifying it as pre-existing.

- [ ] **Step 4: Verify the real Tailscale preflight without changing port 443**

Run:

```powershell
& 'C:\Program Files\Tailscale\tailscale.exe' status --json | ConvertFrom-Json | Select-Object BackendState
& 'C:\Program Files\Tailscale\tailscale.exe' serve status --json
```

Expected: BackendState is `Running`; any existing `:443` entry is recorded as preserved; `:8443` is either empty or already owned by Nova's exact loopback target. Stop and report a conflict if another service owns 8443.

- [ ] **Step 5: Start Nova Anywhere and prove the private route**

Run: `cmd.exe /d /c START_NOVA_ANYWHERE_WINDOWS.bat`

From a second terminal, call the sanitized private URL returned by `/api/desktop/status`:

```powershell
$desktop = Invoke-RestMethod http://127.0.0.1:3000/api/desktop/status
$privateUrl = $desktop.remote_access.private_url
Invoke-RestMethod ($privateUrl + '/api/pairing/status')
```

Expected: local desktop status reports `serve_enabled=true` and `serve_conflict=false`; private pairing status reports `local_client=false` and `pairing_required=true` before pairing. Re-read `tailscale serve status --json` and assert the existing port-443 object is byte-for-byte unchanged while 8443 points to `http://127.0.0.1:3000` without `AllowFunnel`.

- [ ] **Step 6: Prove pair, chat, restart persistence, and revoke**

Create a pairing code only through local `POST /api/pairing/start`, exchange it through the private URL, keep the returned token only in a process-local variable, call private `/api/chat` with that bearer token, and revoke the returned device ID through local `POST /api/pairing/revoke`. Confirm the revoked token receives `401 pairing_required`. Restart Nova through the Anywhere launcher and confirm the private URL is unchanged and the revoked token remains rejected.

Use the fixed test prompt `Reply with the single word READY.` and discard the response after asserting a successful nonempty reply. Do not write the pairing code, token, prompt, or response to the verification report.

- [ ] **Step 7: Verify responsive and offline behavior**

Open the private Companion at 390x844 and desktop Classic at 1440x900. Confirm the remote status link wraps without horizontal overflow, pairing controls remain reachable, the composer remains visible, and Add to Home Screen instructions are present. Stop Nova while leaving Tailscale connected and confirm the phone-facing failure text instructs the user to wake the PC/start Nova/check Tailscale rather than suggesting a public tunnel.

- [ ] **Step 8: Write the content-free verification report and final diff check**

The JSON report schema is:

```json
{
  "schema_version": 1,
  "feature": "nova_tailscale_remote_access",
  "status": "PASS",
  "checks": [
    {"name": "focused_tests", "status": "PASS", "exit_code": 0, "duration_seconds": 0.0},
    {"name": "server_regression", "status": "PASS", "exit_code": 0, "duration_seconds": 0.0},
    {"name": "private_route", "status": "PASS", "reason": "paired_remote_round_trip_verified"},
    {"name": "port_443_preserved", "status": "PASS", "reason": "preexisting_mapping_unchanged"},
    {"name": "revocation", "status": "PASS", "reason": "revoked_token_rejected"},
    {"name": "responsive_pwa", "status": "PASS", "reason": "desktop_and_phone_viewports_verified"}
  ]
}
```

Populate observed durations rather than leaving the sample `0.0` values. Run `git diff --check` across every changed source, UI, launcher, test, and documentation file. Do not claim completion unless every required check has observed evidence; use `LIMITED` for a phone-only check that cannot be physically performed and state the exact remaining user action.

---

## Final Acceptance Checklist

- [ ] Standard Windows launch remains local-only and unchanged in behavior.
- [ ] Anywhere launch binds Nova only to loopback and uses private Tailscale Serve on 8443.
- [ ] Existing Tailscale port-443 configuration remains unchanged.
- [ ] Tailscale-proxied requests never inherit localhost trust.
- [ ] Unpaired and revoked phones are rejected.
- [ ] Paired phone chat works from outside the PC's Wi-Fi while the PC is on.
- [ ] The same private HTTPS origin survives Nova and PC/Tailscale restarts.
- [ ] PWA installation and mobile layout work on the stable private origin.
- [ ] No public tunnel, router forwarding, or backend model port is exposed.
- [ ] Focused, server, launcher, PWA, and full regression checks pass.
- [ ] Verification evidence contains no identity, token, pairing, prompt, answer, or memory content.
