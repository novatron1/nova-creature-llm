from http.server import HTTPServer
import json
from pathlib import Path
from socketserver import ThreadingMixIn
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from nova_foundation import NovaFoundation  # noqa: E402
from nova_reliability import (  # noqa: E402
    ReliabilityError,
    ReliabilityManager,
    apply_pending_foundation_restore,
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


def _request_json(base_url, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        base_url + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _wait_for_job(store, job_id, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = store.get_job(job_id)
        if job and job["status"] in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(0.03)
    raise AssertionError(f"job {job_id} did not finish")


def _make_root(tmp_path):
    root = tmp_path / "nova"
    (root / "data" / "dictionary_memory").mkdir(parents=True)
    (root / "data" / "conversation_memory").mkdir(parents=True)
    (root / "nova_memory").mkdir(parents=True)
    (root / "sandbox" / "app_builder_projects" / "Test_Project").mkdir(parents=True)
    (root / "checkpoints" / "brain_slots").mkdir(parents=True)
    (root / "assets").mkdir(parents=True)

    (root / ".nova_llm_config").write_text("provider=local\n", encoding="utf-8")
    (root / "nova_llm_config.json").write_text('{"provider":"local"}', encoding="utf-8")
    (root / "data" / "nova_memory.json").write_text('{"facts":["safe"]}', encoding="utf-8")
    (root / "data" / "conversation_training_data.jsonl").write_text(
        '{"text":"hello"}\n', encoding="utf-8"
    )
    (root / "data" / "dictionary_memory" / "answers.json").write_text(
        '{"hello":"hi"}', encoding="utf-8"
    )
    (root / "data" / "conversation_memory" / "recent.json").write_text(
        '{"turns":1}', encoding="utf-8"
    )
    (root / "nova_memory" / "long_term_memory.json").write_text(
        '{"memories":[]}', encoding="utf-8"
    )
    (root / "sandbox" / "app_builder_projects" / "Test_Project" / "index.html").write_text(
        "<h1>Nova project</h1>", encoding="utf-8"
    )
    (root / "checkpoints" / "registry.json").write_text('{"models":[]}', encoding="utf-8")
    (root / "nova_chat_web.html").write_text("<!doctype html>", encoding="utf-8")
    (root / "assets" / "nova_foundation_ui.js").write_text("/* ui */", encoding="utf-8")
    (root / "assets" / "nova_foundation_ui.css").write_text("/* ui */", encoding="utf-8")
    (root / "assets" / "nova_app_icon.svg").write_text("<svg/>", encoding="utf-8")
    (root / "manifest.webmanifest").write_text("{}", encoding="utf-8")
    (root / "service-worker.js").write_text("// service worker", encoding="utf-8")
    (root / "offline.html").write_text("<!doctype html>", encoding="utf-8")

    roles = (
        "left_hemisphere",
        "right_hemisphere",
        "memory_transformer",
        "planner_transformer",
        "critic_conscience_transformer",
        "dream_simulation_transformer",
        "speech_output_transformer",
    )
    for role in roles:
        folder = root / "checkpoints" / "brain_slots" / role
        folder.mkdir(parents=True)
        (folder / f"{role}_v055_conversation_trained.pt").write_bytes(b"checkpoint")

    database = root / "data" / "nova_foundation.db"
    connection = sqlite3.connect(database)
    cursor = connection.execute("CREATE TABLE recovery_test(value TEXT NOT NULL)")
    cursor.close()
    cursor = connection.execute("INSERT INTO recovery_test(value) VALUES ('original')")
    connection.commit()
    cursor.close()
    connection.close()
    del cursor, connection
    return root, database


def test_backup_is_verified_and_daily_backup_is_deduplicated(tmp_path):
    root, database = _make_root(tmp_path)
    manager = ReliabilityManager(root, database, retention=4)

    backup = manager.create_backup("manual")

    assert backup["verified"] is True
    assert backup["file_count"] >= 9
    assert backup["source_bytes"] > 0
    archive_path = manager.backup_root / backup["archive"]
    with zipfile.ZipFile(archive_path) as archive:
        manifest = json.loads(archive.read("nova_backup_manifest.json"))
        assert manifest["backup_id"] == backup["backup_id"]
        assert "data/nova_foundation.db" in {item["path"] for item in manifest["files"]}

    first_daily = manager.ensure_daily_backup()
    second_daily = manager.ensure_daily_backup()
    assert first_daily["created"] is True
    assert second_daily["created"] is False
    assert first_daily["backup_id"] == second_daily["backup_id"]


def test_restore_uses_atomic_files_and_stages_database_for_restart(tmp_path):
    root, database = _make_root(tmp_path)
    manager = ReliabilityManager(root, database)
    backup = manager.create_backup("before_change")

    (root / "data" / "nova_memory.json").write_text('{"facts":["changed"]}', encoding="utf-8")
    connection = sqlite3.connect(database)
    cursor = connection.execute("UPDATE recovery_test SET value = 'changed'")
    connection.commit()
    cursor.close()
    connection.close()

    restored = manager.restore_backup(backup["backup_id"])

    assert restored["ok"] is True
    assert restored["restart_required"] is True
    assert manager.get_backup(restored["safety_backup_id"])["reason"] == "pre_restore"
    assert json.loads((root / "data" / "nova_memory.json").read_text(encoding="utf-8")) == {
        "facts": ["safe"]
    }
    connection = sqlite3.connect(database)
    cursor = connection.execute("SELECT value FROM recovery_test")
    assert cursor.fetchone()[0] == "changed"
    cursor.close()
    connection.close()
    del cursor, connection

    restarted = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; sys.path.insert(0, sys.argv[1]); "
                "from nova_reliability import apply_pending_foundation_restore; "
                "raise SystemExit(0 if apply_pending_foundation_restore(sys.argv[2]) else 2)"
            ),
            str(ROOT / "src"),
            str(database),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert restarted.returncode == 0, restarted.stderr
    assert apply_pending_foundation_restore(database) is False
    connection = sqlite3.connect(database)
    cursor = connection.execute("SELECT value FROM recovery_test")
    assert cursor.fetchone()[0] == "original"
    cursor.close()
    connection.close()


def test_invalid_staged_database_preserves_current_database(tmp_path):
    root, database = _make_root(tmp_path)
    pending = database.with_name(database.name + ".restore_pending")
    pending.write_bytes(b"not a sqlite database")

    with pytest.raises(ReliabilityError, match="not a valid SQLite database"):
        apply_pending_foundation_restore(database)

    assert pending.is_file()
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM recovery_test").fetchone()[0] == "original"
    manager = ReliabilityManager(root, database)
    diagnostics = manager.run_diagnostics()
    assert diagnostics["overall"] == "critical"
    assert any(check["id"] == "pending_foundation_restore" for check in diagnostics["checks"])


def test_restore_rejects_tampered_file_before_replacing_live_data(tmp_path):
    root, database = _make_root(tmp_path)
    manager = ReliabilityManager(root, database)
    backup = manager.create_backup("tamper_test")
    archive_path = manager.backup_root / backup["archive"]
    rewritten = archive_path.with_suffix(".rewritten.zip")

    with zipfile.ZipFile(archive_path, "r") as source, zipfile.ZipFile(
        rewritten, "w", compression=zipfile.ZIP_DEFLATED
    ) as destination:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "data/nova_memory.json":
                payload = b'{"facts":["tampered"]}'
            destination.writestr(info, payload)
    rewritten.replace(archive_path)

    (root / "data" / "nova_memory.json").write_text('{"facts":["live"]}', encoding="utf-8")
    with pytest.raises(ReliabilityError, match="(size|checksum) verification failed"):
        manager.restore_backup(backup["backup_id"])
    assert json.loads((root / "data" / "nova_memory.json").read_text(encoding="utf-8")) == {
        "facts": ["live"]
    }


def test_diagnostics_recovery_html_and_retention(tmp_path):
    root, database = _make_root(tmp_path)
    manager = ReliabilityManager(root, database, retention=2)
    for index in range(4):
        manager.create_backup(f"rotation_{index}")

    report = manager.run_diagnostics(host="127.0.0.1", port=3000)

    assert report["ok"] is True
    assert report["counts"]["critical"] == 0
    assert len(manager.list_backups(limit=20)) == 2
    page = manager.recovery_html('<script>alert("unsafe")</script>')
    assert "Nova Recovery" in page
    assert "&lt;script&gt;" in page
    assert '<script>alert("unsafe")</script>' not in page
    healthy_page = manager.recovery_html()
    assert "Nova is running normally" in healthy_page


def test_reliability_http_status_backup_and_restore_guard(monkeypatch, tmp_path):
    root, database = _make_root(tmp_path)
    foundation = NovaFoundation(database)
    reliability = ReliabilityManager(root, database)
    foundation.jobs.register("reliability_backup", server._run_reliability_backup_job)
    foundation.jobs.register("reliability_restore", server._run_reliability_restore_job)
    monkeypatch.setattr(server, "FOUNDATION", foundation)
    monkeypatch.setattr(server, "RELIABILITY", reliability)

    httpd, base_url = _start_test_server(server.NovaHandler)
    try:
        status, payload = _request_json(base_url, "/api/reliability/status")
        assert status == 200
        assert payload["automatic_backups"] is True
        assert payload["backups"] == []

        status, queued = _request_json(
            base_url, "/api/reliability/backup", {"reason": "api_test"}
        )
        assert status == 202
        finished = _wait_for_job(foundation.store, queued["job"]["id"])
        assert finished["status"] == "succeeded"
        assert reliability.list_backups(limit=1)[0]["verified"] is True
        _, refreshed = _request_json(base_url, "/api/reliability/status")
        diagnostics = refreshed["diagnostics"]
        assert diagnostics["ok"] is True
        assert diagnostics["counts"]["critical"] == 0
        assert next(
            check for check in diagnostics["checks"] if check["id"] == "backups"
        )["status"] == "pass"
        assert "files" not in refreshed["latest_backup"]

        with pytest.raises(urllib.error.HTTPError) as denied:
            _request_json(
                base_url,
                "/api/reliability/restore",
                {"backup_id": reliability.list_backups(limit=1)[0]["backup_id"]},
            )
        assert denied.value.code == 400

        with urllib.request.urlopen(base_url + "/recovery", timeout=10) as response:
            assert response.status == 200
            assert response.headers.get_content_type() == "text/html"
            assert b"Nova Recovery" in response.read()
    finally:
        httpd.shutdown()
        httpd.server_close()
