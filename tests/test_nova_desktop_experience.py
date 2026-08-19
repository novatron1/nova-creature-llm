from http.server import HTTPServer
import json
from pathlib import Path
from socketserver import ThreadingMixIn
import sqlite3
import sys
import threading
import urllib.error
import urllib.request

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from nova_backup_vault import BackupVault, MAGIC, VaultError  # noqa: E402
from nova_desktop import DesktopError, NovaDesktopManager, STARTUP_FILENAME  # noqa: E402
from nova_foundation import NovaFoundation  # noqa: E402
from nova_foundation_http import FoundationHttpController  # noqa: E402
from nova_reliability import ReliabilityManager  # noqa: E402
import nova_enhanced_server as server  # noqa: E402


class _ThreadedTestServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _start_test_server(handler):
    httpd = _ThreadedTestServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, f"http://127.0.0.1:{httpd.server_port}"


def _request_json(base_url, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        base_url + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _make_application_root(tmp_path):
    root = tmp_path / "nova"
    (root / "data").mkdir(parents=True)
    (root / "checkpoints").mkdir(parents=True)
    (root / "assets").mkdir(parents=True)
    (root / "tools").mkdir(parents=True)
    (root / ".nova_llm_config").write_text("provider=local\n", encoding="utf-8")
    (root / "nova_llm_config.json").write_text('{"provider":"local"}', encoding="utf-8")
    (root / "data" / "nova_memory.json").write_text(
        '{"facts":["portable"]}', encoding="utf-8"
    )
    (root / "checkpoints" / "registry.json").write_text('{"models":[]}', encoding="utf-8")
    (root / "nova_chat_web.html").write_text("<!doctype html>", encoding="utf-8")
    (root / "assets" / "nova_foundation_ui.js").write_text("/* ui */", encoding="utf-8")
    (root / "assets" / "nova_foundation_ui.css").write_text("/* ui */", encoding="utf-8")
    (root / "assets" / "nova_app_icon.svg").write_text("<svg/>", encoding="utf-8")
    (root / "manifest.webmanifest").write_text("{}", encoding="utf-8")
    (root / "service-worker.js").write_text("// service worker", encoding="utf-8")
    (root / "offline.html").write_text("<!doctype html>", encoding="utf-8")
    (root / "tools" / "nova_autostart.py").write_text("# helper\n", encoding="utf-8")
    return root


class _FakeRemoteAccess:
    def __init__(self):
        self.enabled = False
        self.enable_calls = 0
        self.disable_calls = 0

    def status(self):
        return {
            "ok": True,
            "installed": True,
            "connected": True,
            "serve_enabled": self.enabled,
            "serve_conflict": False,
            "private_url": "https://nova-host.example.ts.net:8443",
            "reason": "ready" if self.enabled else "serve_not_configured",
            "message": "Private phone access is ready.",
        }

    def enable(self):
        self.enable_calls += 1
        self.enabled = True
        return self.status()

    def disable(self):
        self.disable_calls += 1
        self.enabled = False
        return self.status()


def test_desktop_autostart_is_opt_in_reversible_and_owned(tmp_path):
    root = _make_application_root(tmp_path)
    startup = tmp_path / "Startup"
    manager = NovaDesktopManager(
        root, port=8765, startup_directory=startup, platform_name="win32"
    )

    assert manager.status()["autostart_enabled"] is False
    enabled = manager.set_autostart(True)
    startup_file = startup / STARTUP_FILENAME
    content = startup_file.read_text(encoding="utf-8")
    assert enabled["autostart_enabled"] is True
    assert "managed startup v1" in content
    assert str(root) in content
    assert "8765" in content

    manager.set_autostart(True)
    disabled = manager.set_autostart(False)
    assert disabled["autostart_enabled"] is False
    assert not startup_file.exists()


def test_desktop_remote_access_status_and_local_http_controls(monkeypatch, tmp_path):
    root = _make_application_root(tmp_path)
    remote = _FakeRemoteAccess()
    monkeypatch.setenv("NOVA_TRUST_TAILSCALE_SERVE", "true")
    desktop = NovaDesktopManager(
        root,
        port=8765,
        startup_directory=tmp_path / "Startup",
        platform_name="win32",
        remote_access_manager=remote,
    )
    monkeypatch.setattr(server, "DESKTOP", desktop)

    assert desktop.status()["remote_access"]["serve_enabled"] is False
    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        status, enabled = _request_json(
            base_url, "/api/desktop/remote-access", {"enabled": True}
        )
        assert status == 200
        assert enabled["serve_enabled"] is True
        assert remote.enable_calls == 1

        status, disabled = _request_json(
            base_url, "/api/desktop/remote-access", {"enabled": False}
        )
        assert status == 200
        assert disabled["serve_enabled"] is False
        assert remote.disable_calls == 1
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_desktop_refuses_to_enable_remote_access_without_trusted_startup(
    monkeypatch, tmp_path
):
    root = _make_application_root(tmp_path)
    remote = _FakeRemoteAccess()
    desktop = NovaDesktopManager(
        root,
        port=8765,
        startup_directory=tmp_path / "Startup",
        platform_name="win32",
        remote_access_manager=remote,
    )
    monkeypatch.delenv("NOVA_TRUST_TAILSCALE_SERVE", raising=False)

    assert desktop.status()["remote_access"]["management_available"] is False
    with pytest.raises(DesktopError, match="Anywhere launcher"):
        desktop.set_remote_access(True)
    assert remote.enable_calls == 0


def test_pairing_prefers_verified_tailscale_phone_url(monkeypatch, tmp_path):
    foundation = NovaFoundation(tmp_path / "tailscale_pairing.db")
    controller = FoundationHttpController(
        lambda: foundation,
        ROOT,
        remote_phone_url_provider=lambda: "https://nova-host.example.ts.net:8443",
    )
    monkeypatch.setattr(server, "FOUNDATION", foundation)
    monkeypatch.setattr(server, "FOUNDATION_HTTP", controller)

    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        status, created = _request_json(
            base_url, "/api/pairing/start", {"ttl_seconds": 120}
        )
        assert status == 201
        assert created["phone_url"] == "https://nova-host.example.ts.net:8443"
        assert created["pairing_url"].startswith(
            "https://nova-host.example.ts.net:8443/?pair="
        )
        assert created["connection_kind"] == "tailscale"
        assert created["lan_accessible"] is True
        assert created["qr_url"].endswith(".svg")
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_live_server_wires_one_shared_tailscale_manager():
    assert server.DESKTOP.remote_access_manager is server.TAILSCALE
    assert server.TAILSCALE.nova_port == server.DESKTOP.port
    assert callable(server.FOUNDATION_HTTP._remote_phone_url_provider)


def test_live_server_returns_only_an_enabled_private_tailscale_url(monkeypatch):
    class Remote:
        def __init__(self, enabled):
            self.enabled = enabled

        def status(self):
            return {
                "serve_enabled": self.enabled,
                "serve_conflict": False,
                "private_url": "https://nova-host.example.ts.net:8443",
            }

    monkeypatch.setattr(server, "TAILSCALE", Remote(True), raising=False)
    assert server._active_tailscale_url() == "https://nova-host.example.ts.net:8443"

    monkeypatch.setattr(server, "TAILSCALE", Remote(False), raising=False)
    assert server._active_tailscale_url() is None


def test_desktop_autostart_never_deletes_an_unmanaged_conflict(tmp_path):
    root = _make_application_root(tmp_path)
    startup = tmp_path / "Startup"
    startup.mkdir()
    startup_file = startup / STARTUP_FILENAME
    startup_file.write_text("@echo off\necho user-owned\n", encoding="utf-8")
    manager = NovaDesktopManager(
        root, startup_directory=startup, platform_name="win32"
    )

    assert manager.status()["autostart_conflict"] is True
    with pytest.raises(DesktopError, match="unmanaged"):
        manager.set_autostart(False)
    assert "user-owned" in startup_file.read_text(encoding="utf-8")


def test_portable_vault_round_trip_rejects_wrong_password_and_tampering(tmp_path):
    source = tmp_path / "backup.zip"
    plaintext = b"Nova private backup payload\n" * 1000
    source.write_bytes(plaintext)
    vault = BackupVault(tmp_path, export_root=tmp_path / "vaults")
    passphrase = "correct horse nova battery"

    metadata = vault.create(source, "test-backup", passphrase)
    selected = vault.get(metadata["vault_id"])
    assert selected is not None
    _, encrypted_path = selected
    encrypted = encrypted_path.read_bytes()
    assert encrypted.startswith(MAGIC)
    assert plaintext[:80] not in encrypted
    assert passphrase.encode("utf-8") not in encrypted
    assert passphrase not in json.dumps(metadata)
    assert vault.list()[0]["vault_id"] == metadata["vault_id"]

    recovered = tmp_path / "recovered.zip"
    result = vault.decrypt(encrypted_path, recovered, passphrase)
    assert result["bytes"] == len(plaintext)
    assert recovered.read_bytes() == plaintext

    wrong_destination = tmp_path / "wrong.zip"
    with pytest.raises(VaultError, match="incorrect|damaged"):
        vault.decrypt(encrypted_path, wrong_destination, "wrong password for this vault")
    assert not wrong_destination.exists()

    tampered_path = tmp_path / "tampered.novavault"
    tampered = bytearray(encrypted)
    tampered[-20] ^= 0x01
    tampered_path.write_bytes(tampered)
    with pytest.raises(VaultError, match="incorrect|damaged"):
        vault.decrypt(tampered_path, tmp_path / "tampered.zip", passphrase)


def test_desktop_vault_and_pwa_http_endpoints(monkeypatch, tmp_path):
    root = _make_application_root(tmp_path)
    foundation = NovaFoundation(root / "data" / "nova_foundation.db")
    reliability = ReliabilityManager(root, foundation.store.database_path)
    backup = reliability.create_backup("desktop_api_test")
    startup = tmp_path / "Startup"
    desktop = NovaDesktopManager(
        root, port=8765, startup_directory=startup, platform_name="win32"
    )
    monkeypatch.setattr(server, "FOUNDATION", foundation)
    monkeypatch.setattr(server, "RELIABILITY", reliability)
    monkeypatch.setattr(server, "DESKTOP", desktop)

    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        status, desktop_status = _request_json(base_url, "/api/desktop/status")
        assert status == 200
        assert desktop_status["autostart_enabled"] is False

        status, enabled = _request_json(
            base_url, "/api/desktop/autostart", {"enabled": True}
        )
        assert status == 200
        assert enabled["autostart_enabled"] is True
        _, disabled = _request_json(
            base_url, "/api/desktop/autostart", {"enabled": False}
        )
        assert disabled["autostart_enabled"] is False

        passphrase = "api test private passphrase"
        status, created = _request_json(
            base_url,
            "/api/reliability/vault",
            {"backup_id": backup["backup_id"], "passphrase": passphrase},
        )
        assert status == 201
        assert created["vault"]["cipher"] == "AES-256-GCM"
        assert passphrase not in json.dumps(created)
        with urllib.request.urlopen(
            base_url + created["vault"]["download_url"], timeout=20
        ) as response:
            assert response.status == 200
            assert response.headers.get_content_type() == "application/octet-stream"
            assert response.headers["Content-Disposition"].endswith('.novavault"')
            assert response.read(len(MAGIC)) == MAGIC
        assert passphrase.encode("utf-8") not in foundation.store.database_path.read_bytes()

        with pytest.raises(urllib.error.HTTPError) as rejected:
            _request_json(
                base_url,
                "/api/reliability/vault",
                {"backup_id": backup["backup_id"], "passphrase": "too short"},
            )
        assert rejected.value.code == 400

        expected_assets = {
            "/manifest.webmanifest": ("application/manifest+json", None),
            "/service-worker.js": ("application/javascript", "/"),
            "/assets/nova_app_icon.svg": ("image/svg+xml", None),
            "/offline.html": ("text/html", None),
        }
        for path, (content_type, worker_scope) in expected_assets.items():
            with urllib.request.urlopen(base_url + path, timeout=10) as response:
                assert response.status == 200
                assert response.headers.get_content_type() == content_type
                if worker_scope:
                    assert response.headers["Service-Worker-Allowed"] == worker_scope
                assert response.read()
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_pwa_manifest_and_owner_controls_are_wired():
    manifest = json.loads((ROOT / "manifest.webmanifest").read_text(encoding="utf-8"))
    html = (ROOT / "nova_chat_web.html").read_text(encoding="utf-8")
    script = (ROOT / "assets" / "nova_foundation_ui.js").read_text(encoding="utf-8")
    worker = (ROOT / "service-worker.js").read_text(encoding="utf-8")

    assert manifest["display"] == "standalone"
    assert manifest["scope"] == "/"
    assert manifest["icons"][0]["purpose"] == "any maskable"
    assert 'rel="manifest"' in html
    assert 'id="installNovaAppBtn"' in html
    assert 'id="toggleNovaAutostartBtn"' in html
    assert 'id="novaRemoteAccessState"' in html
    assert 'id="novaRemotePhoneUrl"' in html
    assert 'id="copyNovaPhoneUrlBtn"' in html
    assert 'id="toggleNovaRemoteAccessBtn"' in html
    assert 'id="novaVaultDialog"' in html
    assert "beforeinstallprompt" in script
    assert "/api/desktop/autostart" in script
    assert "/api/desktop/remote-access" in script
    assert "renderNovaRemoteAccess" in script
    assert "copyNovaPhoneUrl" in script
    assert "/api/reliability/vault" in script
    assert "NOVA_TRUST_TAILSCALE_SERVE" not in html
    assert "tailcd" not in html.lower()
    assert "nova-shell-2026-08-16-tailscale-v1" in worker
    assert "url.pathname.startsWith('/api/')" in worker


def test_classic_query_panel_allowlist_targets_existing_panels():
    html = (ROOT / "nova_chat_web.html").read_text(encoding="utf-8")
    script = (ROOT / "assets" / "nova_foundation_ui.js").read_text(encoding="utf-8")
    requested_panels = {
        "chat": "chat-panel",
        "settings": "settings-panel",
        "display": "display-panel",
        "dream": "dream-studio-panel",
        "agents": "agent-library-panel",
        "builder": "app-builder-panel",
        "memory": "memory-panel",
        "tools": "tools-panel",
        "research": "research-panel",
        "tests": "test-check-panel",
        "projects": "saved-projects-panel",
        "files": "file-manager-panel",
        "logs": "debug-logs-panel",
    }
    for panel_name, panel_id in requested_panels.items():
        assert f'"{panel_name}": "{panel_id}"' in script
        assert f'id="{panel_id}"' in html
