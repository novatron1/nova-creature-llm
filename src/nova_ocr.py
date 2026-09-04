"""Private, local OCR adapter for Nova picture requests.

The adapter uses the Tesseract command-line interface directly so Nova does not
need Pillow, pytesseract, or another Python package. Uploaded image bytes exist
only in a temporary directory for the duration of the OCR call.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


OCR_INTERFACE_VERSION = "1.0"
_WINDOWS_OCR_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "nova_windows_ocr.ps1"


def _environment_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _timeout_seconds() -> int:
    try:
        value = int(os.environ.get("NOVA_OCR_TIMEOUT_SECONDS", "25") or 25)
    except (TypeError, ValueError):
        value = 25
    return max(5, min(value, 60))


def _candidate_paths() -> list[Path]:
    candidates: list[Path] = []
    configured = str(os.environ.get("NOVA_TESSERACT_COMMAND") or "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())
    discovered = shutil.which("tesseract")
    if discovered:
        candidates.append(Path(discovered))
    if os.name == "nt":
        for variable in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
            root = str(os.environ.get(variable) or "").strip()
            if root:
                candidates.append(Path(root) / "Programs" / "Tesseract-OCR" / "tesseract.exe")
                candidates.append(Path(root) / "Tesseract-OCR" / "tesseract.exe")
    return candidates


def find_tesseract_command() -> str | None:
    """Return a configured or discoverable Tesseract executable path."""

    seen: set[str] = set()
    for candidate in _candidate_paths():
        normalized = os.path.normcase(os.path.abspath(str(candidate)))
        if normalized in seen:
            continue
        seen.add(normalized)
        if candidate.is_file():
            return str(candidate)
    return None


def find_windows_ocr_command() -> str | None:
    """Return PowerShell when the local Windows OCR adapter is usable."""

    if os.name != "nt" or not _WINDOWS_OCR_SCRIPT.is_file():
        return None
    configured = str(os.environ.get("NOVA_POWERSHELL_COMMAND") or "").strip()
    if configured and Path(configured).is_file():
        return configured
    return shutil.which("powershell")


def _available_engine() -> tuple[str | None, str | None]:
    tesseract = find_tesseract_command()
    if tesseract:
        return "tesseract", tesseract
    windows_ocr = find_windows_ocr_command()
    if windows_ocr:
        return "windows_ocr", windows_ocr
    return None, None


def _image_suffix(image_bytes: bytes, mime_type: str) -> str:
    normalized_mime = str(mime_type or "").lower()
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") or "png" in normalized_mime:
        return ".png"
    if image_bytes.startswith((b"GIF87a", b"GIF89a")) or "gif" in normalized_mime:
        return ".gif"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return ".webp"
    return ".jpg"


def _clean_text(value: str, maximum_characters: int) -> str:
    text = str(value or "").replace("\x00", "")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    useful = [line for line in lines if line]
    return "\n".join(useful)[:maximum_characters].strip()


def extract_text(
    image_bytes: bytes,
    *,
    mime_type: str = "",
    language: str = "eng",
    maximum_characters: int = 2000,
) -> tuple[str, dict]:
    """Extract local text and return content plus privacy-safe operational metadata."""

    metadata = {
        "interface_version": OCR_INTERFACE_VERSION,
        "engine": None,
        "available": False,
        "used": False,
        "characters": 0,
        "lines": 0,
        "error": None,
        "content_logged": False,
        "image_persisted": False,
        "local_only": True,
    }
    if not _environment_bool("NOVA_OCR_ENABLED", True):
        metadata["error"] = "disabled"
        return "", metadata
    engine, command = _available_engine()
    if not command:
        metadata["error"] = "engine_unavailable"
        return "", metadata
    metadata["engine"] = engine
    metadata["available"] = True
    if not image_bytes:
        metadata["error"] = "empty_image"
        return "", metadata

    safe_language = re.sub(r"[^a-zA-Z0-9_+.-]", "", str(language or "eng")) or "eng"
    maximum = max(100, min(int(maximum_characters or 2000), 10_000))
    try:
        with tempfile.TemporaryDirectory(prefix="nova-ocr-") as temporary_directory:
            image_path = Path(temporary_directory) / ("picture" + _image_suffix(image_bytes, mime_type))
            image_path.write_bytes(image_bytes)
            command_line = (
                [
                    command,
                    str(image_path),
                    "stdout",
                    "-l",
                    safe_language,
                    "--psm",
                    "6",
                ]
                if engine == "tesseract"
                else [
                    command,
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(_WINDOWS_OCR_SCRIPT),
                    str(image_path),
                ]
            )
            completed = subprocess.run(
                command_line,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_timeout_seconds(),
                check=False,
                shell=False,
                creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
            )
        if completed.returncode != 0:
            metadata["error"] = "recognition_failed"
            return "", metadata
        text = _clean_text(completed.stdout, maximum)
        metadata.update(
            used=bool(text),
            characters=len(text),
            lines=(len(text.splitlines()) if text else 0),
            error=(None if text else "no_text_detected"),
        )
        return text, metadata
    except subprocess.TimeoutExpired:
        metadata["error"] = "timeout"
        return "", metadata
    except Exception:
        metadata["error"] = "engine_error"
        return "", metadata


def health_check() -> dict:
    """Return content-free OCR availability information."""

    enabled = _environment_bool("NOVA_OCR_ENABLED", True)
    engine, command = _available_engine() if enabled else (None, None)
    return {
        "ok": bool(enabled and command),
        "enabled": enabled,
        "engine": engine,
        "interface_version": OCR_INTERFACE_VERSION,
        "local_only": True,
        "content_logged": False,
    }
