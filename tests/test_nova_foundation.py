from email.message import Message
from http.server import HTTPServer
import json
from pathlib import Path
from socketserver import ThreadingMixIn
import sqlite3
import sys
import threading
import time
import urllib.request

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from nova_foundation import (  # noqa: E402
    FoundationStore,
    JobCancelled,
    NovaFoundation,
    PairingError,
    PersistentJobRunner,
)
import nova_enhanced_server as server  # noqa: E402


class _ThreadedTestServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _start_test_server(handler):
    httpd = _ThreadedTestServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, f"http://127.0.0.1:{httpd.server_port}"


def _request_json(base_url, path, payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = urllib.request.Request(
        base_url + path,
        data=data,
        headers=request_headers,
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _wait_for_job(store, job_id, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = store.get_job(job_id)
        if job and job["status"] in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish")


def test_foundation_store_migrates_and_uses_wal(tmp_path):
    store = FoundationStore(tmp_path / "nova_foundation.db")

    health = store.health()

    assert health["ok"] is True
    assert health["schema_version"] == 2
    assert health["journal_mode"] == "wal"


def test_foundation_migrates_existing_paired_devices_to_scoped_schema(tmp_path):
    database = tmp_path / "old_foundation.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            INSERT INTO schema_migrations(version, applied_at)
            VALUES (1, '2026-01-01T00:00:00+00:00');
            CREATE TABLE paired_devices (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                user_agent TEXT,
                created_at TEXT NOT NULL,
                last_seen_at TEXT,
                revoked_at TEXT
            );
            """
        )

    store = FoundationStore(database)

    with sqlite3.connect(database) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(paired_devices)")
        }
    assert store.health()["schema_version"] == 2
    assert "scopes_json" in columns


def test_pairing_codes_are_one_time_and_secrets_are_hashed(tmp_path):
    database = tmp_path / "nova_foundation.db"
    store = FoundationStore(database)
    pairing = store.create_pairing_session()

    with sqlite3.connect(database) as connection:
        stored_code_hash = connection.execute(
            "SELECT code_hash FROM pairing_sessions WHERE id = ?", (pairing["session_id"],)
        ).fetchone()[0]
    assert pairing["code"] not in stored_code_hash

    exchanged = store.exchange_pairing_code(pairing["code"], "Living room phone")
    token = exchanged["token"]
    assert token.startswith("nova_")
    assert store.validate_device_token(token, touch=False)["name"] == "Living room phone"

    with sqlite3.connect(database) as connection:
        stored_token_hash = connection.execute(
            "SELECT token_hash FROM paired_devices WHERE id = ?",
            (exchanged["device"]["id"],),
        ).fetchone()[0]
    assert token not in stored_token_hash
    assert store.validate_device_token(token, touch=False)["scopes"] == []

    device_id = exchanged["device"]["id"]
    assert store.set_device_scopes(
        device_id, ["image.generate", "video.generate"]
    ) == ["image.generate", "video.generate"]
    assert store.validate_device_token(token, touch=False)["scopes"] == [
        "image.generate",
        "video.generate",
    ]
    with pytest.raises(PairingError, match="Unsupported device scopes"):
        store.set_device_scopes(device_id, ["robot.move"])

    with pytest.raises(PairingError, match="invalid|used|expired"):
        store.exchange_pairing_code(pairing["code"], "Second device")

    assert store.revoke_device(exchanged["device"]["id"]) is True
    assert store.validate_device_token(token, touch=False) is None


def test_expired_pairing_code_is_rejected(tmp_path):
    database = tmp_path / "nova_foundation.db"
    store = FoundationStore(database)
    pairing = store.create_pairing_session()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE pairing_sessions SET expires_at = '2000-01-01T00:00:00.000+00:00' WHERE id = ?",
            (pairing["session_id"],),
        )

    with pytest.raises(PairingError, match="invalid or has expired"):
        store.exchange_pairing_code(pairing["code"], "Late phone")


def test_persistent_jobs_succeed_fail_and_cancel(tmp_path):
    store = FoundationStore(tmp_path / "jobs.db")
    runner = PersistentJobRunner(store, max_workers=1)
    started = threading.Event()

    def successful(context, payload):
        context.update(40, "Halfway")
        return {"answer": payload["answer"]}

    def failing(context, payload):
        raise ValueError("expected failure")

    def cancellable(context, payload):
        started.set()
        for _ in range(200):
            if context.cancelled():
                raise JobCancelled("cancelled")
            time.sleep(0.005)
        return {"unexpected": True}

    runner.register("success", successful)
    runner.register("failure", failing)
    runner.register("cancel", cancellable)

    success = runner.start("success", {"answer": 42})
    succeeded = _wait_for_job(store, success["id"])
    assert succeeded["status"] == "succeeded"
    assert succeeded["progress"] == 100
    assert succeeded["result"] == {"answer": 42}

    failure = runner.start("failure")
    failed = _wait_for_job(store, failure["id"])
    assert failed["status"] == "failed"
    assert "ValueError" in failed["error"]

    cancel = runner.start("cancel")
    assert started.wait(timeout=2)
    duplicate = runner.start("cancel")
    assert duplicate["id"] == cancel["id"]
    assert duplicate["deduplicated"] is True
    runner.cancel(cancel["id"])
    cancelled = _wait_for_job(store, cancel["id"])
    assert cancelled["status"] == "cancelled"
    assert store.recent_audit_events()


def test_job_runner_recovers_interrupted_records(tmp_path):
    store = FoundationStore(tmp_path / "jobs.db")
    job = store.create_job("old_work")
    store.update_job(job["id"], status="running", progress=60, message="Working")

    PersistentJobRunner(store)

    recovered = store.get_job(job["id"])
    assert recovered["status"] == "failed"
    assert "restart" in recovered["message"].lower()


def test_pairing_and_job_http_endpoints(monkeypatch, tmp_path):
    foundation = NovaFoundation(tmp_path / "server_foundation.db")
    monkeypatch.setenv("NOVA_PUBLIC_URL", "http://192.168.1.25:3000")

    def self_check(context, payload):
        context.update(75, "Checking")
        return {"ok": True, "summary": {"passed": 3, "total": 3}}

    foundation.jobs.register("full_training_check", self_check)
    monkeypatch.setattr(server, "FOUNDATION", foundation)
    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        with urllib.request.urlopen(
            base_url + "/assets/nova_foundation_ui.css", timeout=10
        ) as response:
            assert response.status == 200
            assert response.headers.get_content_type() == "text/css"
            assert b".foundation-grid" in response.read()
        with urllib.request.urlopen(
            base_url + "/assets/nova_foundation_ui.js", timeout=10
        ) as response:
            assert response.status == 200
            assert response.headers.get_content_type() == "application/javascript"
            assert b"loadFoundationStatus" in response.read()
        with urllib.request.urlopen(
            base_url + "/assets/nova_connection_recovery.js", timeout=10
        ) as response:
            assert response.status == 200
            assert response.headers.get_content_type() == "application/javascript"
            assert b"createNovaConnectionRecovery" in response.read()
        with urllib.request.urlopen(
            base_url + "/assets/nova_dream_studio.css", timeout=10
        ) as response:
            assert response.status == 200
            assert response.headers.get_content_type() == "text/css"
            assert b".dream-studio-grid" in response.read()
        with urllib.request.urlopen(
            base_url + "/assets/nova_dream_studio.js", timeout=10
        ) as response:
            assert response.status == 200
            assert response.headers.get_content_type() == "application/javascript"
            assert b"generateDreamMedia" in response.read()

        status, created = _request_json(base_url, "/api/pairing/start", {"ttl_seconds": 120})
        assert status == 201
        assert len(created["pairing"]["code"]) == 6
        assert created["pairing_url"].endswith("?pair=" + created["pairing"]["code"])
        assert created["qr_url"].endswith(".svg")
        with urllib.request.urlopen(base_url + created["qr_url"], timeout=10) as response:
            assert response.status == 200
            assert response.headers.get_content_type() == "image/svg+xml"
            assert b"<svg" in response.read()

        _, exchanged = _request_json(
            base_url,
            "/api/pairing/exchange",
            {"code": created["pairing"]["code"], "device_name": "Test phone"},
        )
        assert exchanged["token"].startswith("nova_")
        _, pairing_status = _request_json(base_url, "/api/pairing/status")
        assert "token" not in pairing_status
        assert exchanged["token"] not in json.dumps(pairing_status)

        _, devices = _request_json(base_url, "/api/pairing/devices")
        assert [device["name"] for device in devices["devices"]] == ["Test phone"]
        assert devices["devices"][0]["scopes"] == []

        _, scoped = _request_json(
            base_url,
            "/api/pairing/scopes",
            {
                "device_id": exchanged["device"]["id"],
                "scopes": ["image.generate", "video.generate"],
            },
        )
        assert scoped["scopes"] == ["image.generate", "video.generate"]
        _, devices = _request_json(base_url, "/api/pairing/devices")
        assert devices["devices"][0]["scopes"] == [
            "image.generate",
            "video.generate",
        ]

        status, queued = _request_json(
            base_url, "/api/jobs/start", {"kind": "full_training_check", "payload": {}}
        )
        assert status == 202
        finished = _wait_for_job(foundation.store, queued["job"]["id"])
        assert finished["status"] == "succeeded"

        _, jobs = _request_json(base_url, "/api/jobs")
        assert jobs["jobs"][0]["id"] == queued["job"]["id"]

        _, revoked = _request_json(
            base_url,
            "/api/pairing/revoke",
            {"device_id": exchanged["device"]["id"]},
        )
        assert revoked["revoked"] is True
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_remote_client_requires_a_valid_bearer_token(monkeypatch, tmp_path):
    foundation = NovaFoundation(tmp_path / "remote_foundation.db")
    monkeypatch.setattr(server, "FOUNDATION", foundation)
    monkeypatch.delenv("NOVA_REQUIRE_PAIRING", raising=False)
    pairing = foundation.store.create_pairing_session()
    exchanged = foundation.store.exchange_pairing_code(pairing["code"], "Remote phone")

    handler = object.__new__(server.NovaHandler)
    handler.client_address = ("192.168.1.25", 41000)
    handler.headers = Message()
    sent = []
    handler._send_json = lambda payload, status=200: sent.append((status, payload))

    assert handler._authorize_api("/api/chat") is False
    assert sent[-1][0] == 401
    assert sent[-1][1]["code"] == "pairing_required"

    handler.headers["Authorization"] = f"Bearer {exchanged['token']}"
    assert handler._pairing_required_for_client() is False
    assert handler._authorize_api("/api/chat") is True


def test_trusted_proxy_header_keeps_remote_tunnel_client_nonlocal(monkeypatch):
    handler = object.__new__(server.NovaHandler)
    handler.client_address = ("127.0.0.1", 41000)
    handler.headers = Message()
    handler.headers["CF-Connecting-IP"] = "203.0.113.42"

    monkeypatch.delenv("NOVA_TRUST_PROXY_HEADERS", raising=False)
    assert handler._client_is_local() is True

    monkeypatch.setenv("NOVA_TRUST_PROXY_HEADERS", "true")
    assert handler._client_is_local() is False
    assert server.FOUNDATION_HTTP.client_ip(handler) == "203.0.113.42"


def test_cloudflare_loopback_tunnel_is_detected_without_trusting_generic_proxies(monkeypatch):
    handler = object.__new__(server.NovaHandler)
    handler.client_address = ("127.0.0.1", 41000)
    handler.headers = Message()
    handler.headers["CF-Connecting-IP"] = "203.0.113.42"
    handler.headers["CF-Ray"] = "test-IAD"

    monkeypatch.delenv("NOVA_TRUST_PROXY_HEADERS", raising=False)

    assert handler._client_is_local() is False
    assert server.FOUNDATION_HTTP.client_ip(handler) == "203.0.113.42"


def test_tailscale_loopback_proxy_is_remote_only_when_explicitly_trusted(
    monkeypatch, tmp_path
):
    foundation = NovaFoundation(tmp_path / "tailscale_foundation.db")
    monkeypatch.setattr(server, "FOUNDATION", foundation)
    handler = object.__new__(server.NovaHandler)
    handler.client_address = ("127.0.0.1", 41000)
    handler.headers = Message()
    handler.headers["Tailscale-User-Login"] = "phone@example.test"
    sent = []
    handler._send_json = lambda payload, status=200: sent.append((status, payload))

    monkeypatch.delenv("NOVA_TRUST_TAILSCALE_SERVE", raising=False)
    assert handler._client_is_local() is True

    monkeypatch.setenv("NOVA_TRUST_TAILSCALE_SERVE", "true")
    assert handler._client_is_local() is False
    assert server.FOUNDATION_HTTP.client_ip(handler).startswith("tailscale:")
    assert handler._authorize_api("/api/chat") is False
    assert sent[-1][0] == 401
    assert sent[-1][1]["code"] == "pairing_required"


def test_pairing_guess_rate_limit(monkeypatch):
    monkeypatch.setenv("NOVA_PAIRING_ATTEMPT_LIMIT", "3")
    client_key = "test-client-rate-limit"
    server._PAIRING_ATTEMPTS.pop(client_key, None)

    for _ in range(3):
        server._pairing_attempt_allowed(client_key, failed=True)
    allowed, retry_after = server._pairing_attempt_allowed(client_key)

    assert allowed is False
    assert retry_after > 0
    server._pairing_attempt_allowed(client_key, succeeded=True)
    assert server._pairing_attempt_allowed(client_key)[0] is True


def test_foundation_controls_are_present_in_ui():
    html = (ROOT / "nova_chat_web.html").read_text(encoding="utf-8")
    ui_script = (ROOT / "assets" / "nova_foundation_ui.js").read_text(encoding="utf-8")
    ui_styles = (ROOT / "assets" / "nova_foundation_ui.css").read_text(encoding="utf-8")
    dream_script = (ROOT / "assets" / "nova_dream_studio.js").read_text(encoding="utf-8")
    dream_styles = (ROOT / "assets" / "nova_dream_studio.css").read_text(encoding="utf-8")

    assert 'id="pairingCodeInput"' in html
    assert 'id="pairedDeviceList"' in html
    assert 'id="foundationJobList"' in html
    assert 'id="pairingQrWrap"' in html
    assert 'id="reliabilityCheckList"' in html
    assert 'id="reliabilityBackupList"' in html
    assert 'id="novaRemoteAccessState"' in html
    assert 'id="novaRemotePhoneUrl"' in html
    assert 'id="copyNovaPhoneUrlBtn"' in html
    assert 'id="toggleNovaRemoteAccessBtn"' in html
    assert 'href="assets/nova_foundation_ui.css"' in html
    assert 'src="assets/nova_foundation_ui.js"' in html
    assert 'href="assets/nova_dream_studio.css"' in html
    assert 'src="assets/nova_dream_studio.js"' in html
    assert 'id="dreamStudioSteps" type="number" min="1" max="200" value="8"' in html
    assert "NOVA_DEVICE_TOKEN_KEY" in ui_script
    assert "authHeaders" in ui_script
    assert "/api/jobs/start" in ui_script
    assert "/api/reliability/backup" in ui_script
    assert "/api/reliability/restore" in ui_script
    assert "/api/pairing/scopes" in ui_script
    assert "setPairedDeviceMediaAccess" in ui_script
    assert "renderNovaRemoteAccess" in ui_script
    assert "copyNovaPhoneUrl" in ui_script
    assert "toggleNovaRemoteAccess" in ui_script
    assert "['image.generate','video.generate']" in ui_script
    assert "forgetPairedDeviceToken" in ui_script
    assert "isNovaLoopbackUrl" in html
    assert "novaFetchWithTimeout" in html
    assert "res.status === 401 && isNovaLoopbackUrl(url)" in html
    assert "Promise.allSettled([" in html
    assert "/nova/v1/images/generations" in dream_script
    assert "/nova/v1/videos/generations" in dream_script
    assert "/nova/v1/media/access" in dream_script
    assert "/nova/v1/jobs?limit=25" in dream_script
    assert "novaFetchWithTimeout" in dream_script
    assert "DREAM_STUDIO_REQUEST_TIMEOUT_MS" in dream_script
    assert "/api/gpu-hub/status" in dream_script
    assert "dreamStudioGpuState" in dream_script
    assert "URL.createObjectURL" in dream_script
    assert ".dream-studio-grid" in dream_styles
    assert "applyPairingLink" in ui_script
    pairing_required_function = ui_script.split("function showPairingRequired", 1)[1].split(
        "function friendlyFoundationTime", 1
    )[0]
    assert "if(pairingExchangeInProgress) return;" in pairing_required_function
    assert "if(!settingsPanel?.classList.contains('active')) openPanel('settings-panel');" in pairing_required_function
    assert "clearPairedDeviceToken();" not in pairing_required_function
    assert "const authorized = await loadFoundationStatus();" in html
    assert "if(!authorized) return;" in html
    assert ".foundation-grid" in ui_styles
    assert ".pairing-qr-wrap" in ui_styles
    assert ".reliability-check" in ui_styles
