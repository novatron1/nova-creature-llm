from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import nova_ocr


def test_extract_text_uses_temporary_image_and_never_logs_content(monkeypatch, tmp_path):
    executable = tmp_path / "tesseract.exe"
    executable.write_bytes(b"test")
    monkeypatch.setenv("NOVA_TESSERACT_COMMAND", str(executable))
    observed = {}

    def fake_run(command, **kwargs):
        image_path = Path(command[1])
        observed["image_path"] = image_path
        observed["bytes"] = image_path.read_bytes()
        observed["command"] = command
        observed["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout="Nova Creature\nChat Home\n", stderr="")

    monkeypatch.setattr(nova_ocr.subprocess, "run", fake_run)

    text, metadata = nova_ocr.extract_text(
        b"\x89PNG\r\n\x1a\nprivate-image",
        mime_type="image/png",
    )

    assert text == "Nova Creature\nChat Home"
    assert observed["bytes"].startswith(b"\x89PNG")
    assert observed["command"][2:] == ["stdout", "-l", "eng", "--psm", "6"]
    assert observed["kwargs"]["shell"] is False
    assert observed["image_path"].exists() is False
    assert metadata == {
        "interface_version": "1.0",
        "engine": "tesseract",
        "available": True,
        "used": True,
        "characters": 23,
        "lines": 2,
        "error": None,
        "content_logged": False,
        "image_persisted": False,
        "local_only": True,
    }


def test_extract_text_reports_unavailable_without_writing_image(monkeypatch):
    monkeypatch.delenv("NOVA_TESSERACT_COMMAND", raising=False)
    monkeypatch.setattr(nova_ocr, "_candidate_paths", lambda: [])
    monkeypatch.setattr(nova_ocr, "find_windows_ocr_command", lambda: None)
    monkeypatch.setattr(
        nova_ocr.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("missing OCR engine must not be executed")
        ),
    )

    text, metadata = nova_ocr.extract_text(b"private-image", mime_type="image/jpeg")

    assert text == ""
    assert metadata["available"] is False
    assert metadata["used"] is False
    assert metadata["error"] == "engine_unavailable"
    assert metadata["content_logged"] is False


def test_health_check_is_content_free(monkeypatch, tmp_path):
    executable = tmp_path / "tesseract.exe"
    executable.write_bytes(b"test")
    monkeypatch.setenv("NOVA_TESSERACT_COMMAND", str(executable))

    assert nova_ocr.health_check() == {
        "ok": True,
        "enabled": True,
        "engine": "tesseract",
        "interface_version": "1.0",
        "local_only": True,
        "content_logged": False,
    }


def test_windows_ocr_is_local_fallback_when_tesseract_is_missing(monkeypatch, tmp_path):
    powershell = tmp_path / "powershell.exe"
    powershell.write_bytes(b"test")
    monkeypatch.setattr(nova_ocr, "find_tesseract_command", lambda: None)
    monkeypatch.setattr(nova_ocr, "find_windows_ocr_command", lambda: str(powershell))
    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["image_path"] = Path(command[-1])
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="Nova Creature\nRaw Compare",
            stderr="",
        )

    monkeypatch.setattr(nova_ocr.subprocess, "run", fake_run)

    text, metadata = nova_ocr.extract_text(b"jpeg-data", mime_type="image/jpeg")

    assert text == "Nova Creature\nRaw Compare"
    assert observed["command"][0] == str(powershell)
    assert observed["command"][1:6] == [
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
    ]
    assert observed["command"][6] == str(nova_ocr._WINDOWS_OCR_SCRIPT)
    assert observed["image_path"].exists() is False
    assert metadata["engine"] == "windows_ocr"
    assert metadata["used"] is True
    assert metadata["content_logged"] is False
