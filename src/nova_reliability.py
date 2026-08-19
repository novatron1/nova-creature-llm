"""Backup, restore, diagnostics, and recovery support for Nova.

The Reliability Manager is intentionally independent of Nova's in-memory chat
state.  It snapshots durable user data, verifies every archived file, restores
through atomic replacements, and reports when an application restart is needed
to reload restored state.
"""

from __future__ import annotations

import hashlib
from html import escape
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import socket
import sqlite3
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from typing import Any, Iterable
import uuid
import zipfile

from nova_backup_vault import BackupVault, VaultError, encryption_available


BACKUP_FORMAT_VERSION = 1
DEFAULT_RETENTION = 7
ROLE_NAMES = (
    "left_hemisphere",
    "right_hemisphere",
    "memory_transformer",
    "planner_transformer",
    "critic_conscience_transformer",
    "dream_simulation_transformer",
    "speech_output_transformer",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime | None = None) -> str:
    return (value or _utc_now()).isoformat(timespec="seconds")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def _is_enabled(name: str, default: str = "on") -> bool:
    return str(os.environ.get(name, default)).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }


class ReliabilityError(RuntimeError):
    """An expected reliability operation could not be completed safely."""


class ReliabilityManager:
    """Own Nova's coordinated backup and startup-health lifecycle."""

    def __init__(
        self,
        application_root: str | Path,
        foundation_database: str | Path,
        *,
        backup_root: str | Path | None = None,
        retention: int = DEFAULT_RETENTION,
    ):
        self.root = Path(application_root).expanduser().resolve()
        self.foundation_database = Path(foundation_database).expanduser().resolve()
        self.backup_root = Path(
            backup_root or (self.root / "backups" / "reliability")
        ).expanduser().resolve()
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self.retention = max(2, min(int(retention), 30))
        self._operation_lock = threading.Lock()
        self._automatic_stop = threading.Event()
        self._automatic_thread: threading.Thread | None = None
        self.last_diagnostics: dict[str, Any] | None = None
        self.vault = BackupVault(self.root)

    @property
    def automatic_enabled(self) -> bool:
        return _is_enabled("NOVA_AUTOMATIC_BACKUPS", "on")

    def backup_sources(self) -> list[Path]:
        paths = [
            self.root / ".nova_llm_config",
            self.root / "nova_llm_config.json",
            self.root / "data" / "nova_memory.json",
            self.root / "data" / "conversation_training_data.jsonl",
            self.root / "data" / "dictionary_memory",
            self.root / "data" / "conversation_memory",
            self.root / "nova_memory" / "long_term_memory.json",
            self.root / "sandbox" / "app_builder_projects",
        ]
        return [path for path in paths if path.exists()]

    def _iter_source_files(self, paths: Iterable[Path]) -> Iterable[Path]:
        seen: set[Path] = set()
        try:
            max_file_bytes = max(
                1, min(int(os.environ.get("NOVA_BACKUP_MAX_FILE_MB", "256")), 2048)
            ) * 1024 * 1024
        except (TypeError, ValueError):
            max_file_bytes = 256 * 1024 * 1024
        for path in paths:
            candidates = [path] if path.is_file() else path.rglob("*")
            for candidate in candidates:
                try:
                    resolved = candidate.resolve()
                    relative = resolved.relative_to(self.root)
                except (OSError, ValueError):
                    continue
                if resolved in seen or not resolved.is_file() or resolved.is_symlink():
                    continue
                if "__pycache__" in relative.parts or ".git" in relative.parts:
                    continue
                if relative.parts[:2] == ("nova_memory", "backups"):
                    continue
                try:
                    if resolved.stat().st_size > max_file_bytes:
                        continue
                except OSError:
                    continue
                seen.add(resolved)
                yield resolved

    def _snapshot_foundation_database(self, destination: Path) -> bool:
        if not self.foundation_database.is_file():
            return False
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_connection = sqlite3.connect(
            f"file:{self.foundation_database.as_posix()}?mode=ro", uri=True, timeout=10
        )
        destination_connection = sqlite3.connect(str(destination), timeout=10)
        try:
            source_connection.backup(destination_connection)
        finally:
            destination_connection.close()
            source_connection.close()
        return True

    def create_backup(self, reason: str = "manual", *, rotate: bool = True) -> dict[str, Any]:
        if not self._operation_lock.acquire(blocking=False):
            raise ReliabilityError("Another backup or restore operation is already running.")
        try:
            result = self._create_backup_locked(reason=reason, rotate=rotate)
        finally:
            self._operation_lock.release()
        try:
            self.run_diagnostics()
        except Exception:
            # A completed, verified backup remains valid even if a secondary
            # health read cannot refresh immediately.
            pass
        return result

    def _create_backup_locked(self, reason: str, *, rotate: bool) -> dict[str, Any]:
        now = _utc_now()
        backup_id = now.strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8]
        archive_path = self.backup_root / f"nova_backup_{backup_id}.zip"
        metadata_path = self.backup_root / f"nova_backup_{backup_id}.json"
        temporary_archive = archive_path.with_suffix(".zip.tmp")
        files: list[dict[str, Any]] = []
        total_bytes = 0

        try:
            with tempfile.TemporaryDirectory(prefix="nova-reliability-") as temp_name:
                temp_root = Path(temp_name)
                database_snapshot = temp_root / "data" / "nova_foundation.db"
                database_available = self._snapshot_foundation_database(database_snapshot)
                sources = list(self._iter_source_files(self.backup_sources()))
                if database_available:
                    sources.append(database_snapshot)
                if not sources:
                    raise ReliabilityError("No durable Nova data was available to back up.")

                with zipfile.ZipFile(
                    temporary_archive,
                    "w",
                    compression=zipfile.ZIP_DEFLATED,
                    compresslevel=6,
                    allowZip64=True,
                ) as archive:
                    for source in sorted(sources, key=lambda item: str(item).lower()):
                        if source == database_snapshot:
                            archive_name = "data/nova_foundation.db"
                        else:
                            archive_name = source.relative_to(self.root).as_posix()
                        digest = hashlib.sha256()
                        size = 0
                        with source.open("rb") as input_stream, archive.open(
                            archive_name, "w"
                        ) as output_stream:
                            for chunk in iter(lambda: input_stream.read(1024 * 1024), b""):
                                digest.update(chunk)
                                size += len(chunk)
                                output_stream.write(chunk)
                        files.append(
                            {"path": archive_name, "size": size, "sha256": digest.hexdigest()}
                        )
                        total_bytes += size

                    manifest = {
                        "format_version": BACKUP_FORMAT_VERSION,
                        "backup_id": backup_id,
                        "created_at": _timestamp(now),
                        "reason": str(reason or "manual")[:80],
                        "file_count": len(files),
                        "source_bytes": total_bytes,
                        "files": files,
                    }
                    archive.writestr("nova_backup_manifest.json", _json_bytes(manifest))

                os.replace(temporary_archive, archive_path)
                metadata = {
                    **manifest,
                    "archive": archive_path.name,
                    "archive_bytes": archive_path.stat().st_size,
                    "verified": True,
                }
                temporary_metadata = metadata_path.with_suffix(".json.tmp")
                temporary_metadata.write_bytes(_json_bytes(metadata))
                os.replace(temporary_metadata, metadata_path)
        except Exception:
            temporary_archive.unlink(missing_ok=True)
            archive_path.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
            raise

        if rotate:
            self._rotate_backups()
        return self.get_backup(backup_id) or metadata

    def ensure_daily_backup(self) -> dict[str, Any]:
        today = _utc_now().date()
        for backup in self.list_backups(limit=100):
            try:
                created = datetime.fromisoformat(backup["created_at"]).date()
            except (KeyError, TypeError, ValueError):
                continue
            if created == today and backup.get("reason") == "daily":
                return {**backup, "created": False}
        created = self.create_backup("daily")
        return {**created, "created": True}

    def start_automatic_backups(self) -> bool:
        if not self.automatic_enabled:
            return False
        if self._automatic_thread and self._automatic_thread.is_alive():
            return True
        self._automatic_stop.clear()

        def worker() -> None:
            while not self._automatic_stop.is_set():
                try:
                    self.ensure_daily_backup()
                except Exception:
                    # The diagnostics/status endpoint exposes backup health. A
                    # daemon maintenance loop must never take down the app.
                    pass
                self._automatic_stop.wait(60 * 60)

        self._automatic_thread = threading.Thread(
            target=worker, name="nova-daily-backup", daemon=True
        )
        self._automatic_thread.start()
        return True

    def stop_automatic_backups(self) -> None:
        self._automatic_stop.set()

    def _rotate_backups(self) -> None:
        backups = self.list_backups(limit=1000)
        for backup in backups[self.retention :]:
            backup_id = backup.get("backup_id")
            if not backup_id:
                continue
            (self.backup_root / f"nova_backup_{backup_id}.zip").unlink(missing_ok=True)
            (self.backup_root / f"nova_backup_{backup_id}.json").unlink(missing_ok=True)

    def list_backups(self, limit: int = 25) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 1000))
        results: list[dict[str, Any]] = []
        for metadata_path in self.backup_root.glob("nova_backup_*.json"):
            try:
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
                archive = self.backup_root / str(payload.get("archive") or "")
                if archive.is_file() and payload.get("backup_id"):
                    results.append(payload)
            except (OSError, ValueError, TypeError):
                continue
        results.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return results[:safe_limit]

    def get_backup(self, backup_id: str) -> dict[str, Any] | None:
        normalized = str(backup_id or "").strip()
        if not normalized or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in normalized):
            return None
        metadata_path = self.backup_root / f"nova_backup_{normalized}.json"
        archive_path = self.backup_root / f"nova_backup_{normalized}.zip"
        if not metadata_path.is_file() or not archive_path.is_file():
            return None
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        return payload if payload.get("backup_id") == normalized else None

    def restore_backup(self, backup_id: str) -> dict[str, Any]:
        selected = self.get_backup(backup_id)
        if selected is None:
            raise ReliabilityError("Backup not found.")

        safety_backup = self.create_backup("pre_restore", rotate=False)
        if not self._operation_lock.acquire(blocking=False):
            raise ReliabilityError("Another backup or restore operation is already running.")
        try:
            archive_path = self.backup_root / selected["archive"]
            restored_files = self._restore_archive_locked(archive_path)
            self._append_restore_history(
                {
                    "restored_at": _timestamp(),
                    "backup_id": backup_id,
                    "safety_backup_id": safety_backup["backup_id"],
                    "restored_files": restored_files,
                }
            )
        finally:
            self._operation_lock.release()
        return {
            "ok": True,
            "backup_id": backup_id,
            "safety_backup_id": safety_backup["backup_id"],
            "restored_files": restored_files,
            "restart_required": True,
            "message": "Backup restored. Restart Nova to load all restored memory and settings.",
        }

    def create_vault_export(self, backup_id: str, passphrase: Any) -> dict[str, Any]:
        if not self._operation_lock.acquire(blocking=False):
            raise ReliabilityError("Another backup, restore, or vault operation is running.")
        try:
            selected = self.get_backup(backup_id)
            if selected is None:
                raise ReliabilityError("Backup not found.")
            archive_path = self.backup_root / str(selected["archive"])
            return self.vault.create(archive_path, backup_id, passphrase)
        finally:
            self._operation_lock.release()

    def list_vault_exports(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.vault.list(limit=limit)

    def get_vault_export(self, vault_id: str) -> tuple[dict[str, Any], Path] | None:
        return self.vault.get(vault_id)

    def _restore_archive_locked(self, archive_path: Path) -> int:
        with tempfile.TemporaryDirectory(prefix="nova-restore-") as temp_name:
            temp_root = Path(temp_name)
            with zipfile.ZipFile(archive_path, "r") as archive:
                try:
                    manifest = json.loads(
                        archive.read("nova_backup_manifest.json").decode("utf-8")
                    )
                except (KeyError, UnicodeDecodeError, ValueError) as exc:
                    raise ReliabilityError("Backup manifest is missing or invalid.") from exc
                if manifest.get("format_version") != BACKUP_FORMAT_VERSION:
                    raise ReliabilityError("Backup format is not supported by this Nova version.")
                file_entries = manifest.get("files")
                if not isinstance(file_entries, list) or not file_entries:
                    raise ReliabilityError("Backup contains no restorable files.")
                for entry in file_entries:
                    relative = self._safe_archive_relative(entry.get("path"))
                    destination = temp_root.joinpath(*relative.parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        source = archive.open(relative.as_posix(), "r")
                    except KeyError as exc:
                        raise ReliabilityError(
                            f"Backup file is missing: {relative.as_posix()}"
                        ) from exc
                    with source, destination.open("wb") as output:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
                    if destination.stat().st_size != int(entry.get("size") or -1):
                        raise ReliabilityError(
                            f"Backup size verification failed: {relative.as_posix()}"
                        )
                    if _sha256_file(destination) != str(entry.get("sha256") or ""):
                        raise ReliabilityError(
                            f"Backup checksum verification failed: {relative.as_posix()}"
                        )

            database_source = temp_root / "data" / "nova_foundation.db"
            restored = 0
            for entry in manifest["files"]:
                relative = self._safe_archive_relative(entry["path"])
                source = temp_root.joinpath(*relative.parts)
                if relative.as_posix() == "data/nova_foundation.db":
                    continue
                destination = (self.root / Path(*relative.parts)).resolve()
                try:
                    destination.relative_to(self.root)
                except ValueError as exc:
                    raise ReliabilityError("Restore destination escaped Nova's workspace.") from exc
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_name(
                    destination.name + ".restore_" + uuid.uuid4().hex[:8]
                )
                shutil.copy2(source, temporary)
                os.replace(temporary, destination)
                restored += 1

            if database_source.is_file():
                self._stage_foundation_database_restore(database_source)
                restored += 1
            return restored

    @staticmethod
    def _safe_archive_relative(value: Any) -> PurePosixPath:
        relative = PurePosixPath(str(value or ""))
        if (
            not relative.parts
            or relative.is_absolute()
            or ".." in relative.parts
            or "." in relative.parts
        ):
            raise ReliabilityError("Backup contains an unsafe path.")
        return relative

    def _stage_foundation_database_restore(self, source_path: Path) -> None:
        """Stage the live job database for replacement on the next clean startup."""
        pending = self.foundation_database.with_name(
            self.foundation_database.name + ".restore_pending"
        )
        temporary = pending.with_name(pending.name + ".tmp")
        shutil.copy2(source_path, temporary)
        os.replace(temporary, pending)

    def _append_restore_history(self, event: dict[str, Any]) -> None:
        path = self.backup_root / "restore_history.jsonl"
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    def run_diagnostics(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        port_error: str | None = None,
    ) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []

        def add(check_id: str, status: str, message: str, detail: Any = None) -> None:
            item = {"id": check_id, "status": status, "message": message}
            if detail is not None:
                item["detail"] = detail
            checks.append(item)

        python_ok = sys.version_info >= (3, 10)
        add(
            "python",
            "pass" if python_ok else "critical",
            f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )

        try:
            disk = shutil.disk_usage(self.root)
            free_gb = round(disk.free / (1024**3), 2)
            disk_status = "critical" if disk.free < 500 * 1024 * 1024 else ("warning" if disk.free < 2 * 1024**3 else "pass")
            add("disk", disk_status, f"{free_gb} GB free", {"free_bytes": disk.free})
        except OSError as exc:
            add("disk", "warning", "Could not measure free disk space", str(exc))

        writable_target = self.root / "data" / "reliability_write_test.tmp"
        try:
            writable_target.parent.mkdir(parents=True, exist_ok=True)
            writable_target.write_text("ok", encoding="utf-8")
            writable_target.unlink(missing_ok=True)
            add("storage_writable", "pass", "Nova data folders are writable")
        except OSError as exc:
            add("storage_writable", "critical", "Nova data folders are not writable", str(exc))

        for relative in (
            Path("nova_llm_config.json"),
            Path("data/nova_memory.json"),
            Path("checkpoints/registry.json"),
        ):
            path = self.root / relative
            if not path.is_file():
                add(f"json:{relative.as_posix()}", "warning", f"Missing {relative.as_posix()}")
                continue
            try:
                json.loads(path.read_text(encoding="utf-8"))
                add(f"json:{relative.as_posix()}", "pass", f"Valid {relative.as_posix()}")
            except (OSError, UnicodeDecodeError, ValueError) as exc:
                add(f"json:{relative.as_posix()}", "critical", f"Invalid {relative.as_posix()}", str(exc))

        missing_roles = []
        for role in ROLE_NAMES:
            checkpoint = (
                self.root
                / "checkpoints"
                / "brain_slots"
                / role
                / f"{role}_v055_conversation_trained.pt"
            )
            if not checkpoint.is_file():
                missing_roles.append(role)
        add(
            "brain_checkpoints",
            "pass" if not missing_roles else "warning",
            "All seven current brain checkpoints are present"
            if not missing_roles
            else f"Missing {len(missing_roles)} current brain checkpoint(s)",
            {"missing_roles": missing_roles},
        )

        required_assets = (
            self.root / "nova_chat_web.html",
            self.root / "assets" / "nova_foundation_ui.js",
            self.root / "assets" / "nova_foundation_ui.css",
        )
        missing_assets = [path.name for path in required_assets if not path.is_file()]
        add(
            "ui_assets",
            "pass" if not missing_assets else "critical",
            "Nova UI assets are present" if not missing_assets else "Nova UI assets are missing",
            {"missing": missing_assets},
        )

        app_assets = (
            self.root / "assets" / "nova_app_icon.svg",
            self.root / "manifest.webmanifest",
            self.root / "service-worker.js",
            self.root / "offline.html",
        )
        missing_app_assets = [path.name for path in app_assets if not path.is_file()]
        add(
            "installable_app",
            "pass" if not missing_app_assets else "warning",
            "Installable desktop and phone shell is ready"
            if not missing_app_assets
            else "Installable app extras are incomplete; browser chat still works",
            {"missing": missing_app_assets},
        )

        pending_restore = self.foundation_database.with_name(
            self.foundation_database.name + ".restore_pending"
        )
        if pending_restore.is_file():
            add(
                "pending_foundation_restore",
                "critical",
                "A staged Foundation restore could not be applied; the current database was preserved",
            )

        try:
            import qrcode  # noqa: F401
            import qrcode.image.svg  # noqa: F401

            add("qr_pairing", "pass", "Offline QR pairing support is available")
        except Exception:
            add("qr_pairing", "warning", "QR package unavailable; manual pairing still works")

        add(
            "encrypted_vaults",
            "pass" if encryption_available() else "warning",
            "AES-256 portable backup encryption is available"
            if encryption_available()
            else "Encrypted portable exports need the runtime encryption package",
        )

        backups = self.list_backups(limit=1)
        if backups:
            add("backups", "pass", "Verified backup available", {"latest": backups[0]["created_at"]})
        else:
            add("backups", "warning", "No coordinated reliability backup exists yet")

        if port_error:
            add("port", "critical", f"Nova could not use port {port}", port_error)
        elif host is not None and port is not None:
            add("port", "pass", f"Requested address {host}:{port} passed startup validation")

        counts = {
            "pass": sum(item["status"] == "pass" for item in checks),
            "warning": sum(item["status"] == "warning" for item in checks),
            "critical": sum(item["status"] == "critical" for item in checks),
        }
        overall = "critical" if counts["critical"] else ("degraded" if counts["warning"] else "healthy")
        report = {
            "ok": counts["critical"] == 0,
            "overall": overall,
            "checked_at": _timestamp(),
            "counts": counts,
            "checks": checks,
        }
        self.last_diagnostics = report
        return report

    def status(self) -> dict[str, Any]:
        backups = self.list_backups(limit=20)
        summaries = [self._backup_summary(backup) for backup in backups]
        vault_exports = self.list_vault_exports(limit=20)
        return {
            "ok": True,
            "automatic_backups": self.automatic_enabled,
            "retention": self.retention,
            "backup_count": len(self.list_backups(limit=1000)),
            "latest_backup": summaries[0] if summaries else None,
            "backups": summaries,
            "encryption_available": encryption_available(),
            "vault_count": len(self.list_vault_exports(limit=100)),
            "vault_exports": vault_exports,
            "diagnostics": self.last_diagnostics or self.run_diagnostics(),
        }

    @staticmethod
    def _backup_summary(backup: dict[str, Any]) -> dict[str, Any]:
        allowed = (
            "backup_id",
            "created_at",
            "reason",
            "file_count",
            "source_bytes",
            "archive_bytes",
            "verified",
        )
        return {key: backup.get(key) for key in allowed}

    def recovery_html(self, error: str | None = None) -> str:
        diagnostics = self.last_diagnostics or self.run_diagnostics(port_error=error)
        needs_recovery = bool(error) or diagnostics.get("overall") == "critical"
        recovery_note = (
            "Nova protected your data and stopped normal startup. Fix the critical item below, then restart Nova."
            if needs_recovery
            else "Nova is running normally. This read-only recovery view confirms that its essential files and backups are ready."
        )
        rows = []
        for check in diagnostics.get("checks", []):
            rows.append(
                '<div class="check '
                + escape(str(check.get("status") or "warning"))
                + '"><strong>'
                + escape(str(check.get("message") or check.get("id") or "Check"))
                + "</strong><span>"
                + escape(str(check.get("status") or "warning").upper())
                + "</span></div>"
            )
        error_html = (
            '<div class="error"><strong>Startup issue:</strong> '
            + escape(str(error))
            + "</div>"
            if error
            else ""
        )
        return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nova Recovery</title><style>
body{margin:0;background:#090914;color:#f3f3ff;font:15px/1.45 system-ui,sans-serif}main{max-width:760px;margin:40px auto;padding:24px}
.panel{background:#15152a;border:1px solid #393970;border-radius:18px;padding:22px;box-shadow:0 18px 60px #0008}h1{margin:0 0 8px}.note{color:#bfc1df;margin-bottom:18px}
.error{border:1px solid #7d3345;background:#321721;color:#ffc1cd;padding:12px;border-radius:12px;margin-bottom:14px}.checks{display:grid;gap:8px}
.check{display:flex;justify-content:space-between;gap:14px;border:1px solid #30305d;background:#0d0d1b;border-radius:10px;padding:10px}.check span{font-size:11px;color:#8effb9}.check.warning span{color:#ffd27d}.check.critical span{color:#ff9baa}
</style></head><body><main><section class="panel"><h1>Nova Recovery</h1><p class="note">""" + escape(recovery_note) + "</p>" + error_html + '<div class="checks">' + "".join(rows) + "</div></section></main></body></html>"


def port_appears_available(host: str, port: int) -> bool:
    target = "127.0.0.1" if host in {"0.0.0.0", "::", "localhost"} else host
    family = socket.AF_INET6 if ":" in target else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as connection:
            connection.settimeout(0.2)
            return connection.connect_ex((target, int(port))) != 0
    except OSError:
        return True


def apply_pending_foundation_restore(database_path: str | Path) -> bool:
    """Apply a verified staged Foundation database before workers are started."""
    database = Path(database_path).expanduser().resolve()
    pending = database.with_name(database.name + ".restore_pending")
    if not pending.is_file():
        return False
    verification_copy = pending.with_name(
        pending.name + ".verify_" + uuid.uuid4().hex[:8]
    )
    try:
        shutil.copy2(pending, verification_copy)
        source_connection = sqlite3.connect(
            f"file:{verification_copy.as_posix()}?mode=ro&immutable=1",
            uri=True,
            timeout=10,
        )
        try:
            integrity_cursor = source_connection.execute("PRAGMA quick_check")
            try:
                integrity = integrity_cursor.fetchone()
            finally:
                integrity_cursor.close()
            if not integrity or str(integrity[0]).lower() != "ok":
                raise ReliabilityError(
                    "The staged Foundation database failed its integrity check."
                )
        finally:
            source_connection.close()
    except sqlite3.DatabaseError as exc:
        raise ReliabilityError(
            "The staged Foundation database is not a valid SQLite database."
        ) from exc
    finally:
        verification_copy.unlink(missing_ok=True)
        verification_copy.with_name(verification_copy.name + "-wal").unlink(missing_ok=True)
        verification_copy.with_name(verification_copy.name + "-shm").unlink(missing_ok=True)

    database.parent.mkdir(parents=True, exist_ok=True)
    database.with_name(database.name + "-wal").unlink(missing_ok=True)
    database.with_name(database.name + "-shm").unlink(missing_ok=True)
    for attempt in range(10):
        try:
            os.replace(pending, database)
            break
        except PermissionError:
            if attempt == 9:
                raise
            # Windows virus scanners and recently closed SQLite readers can
            # briefly retain a file handle even after the connection closes.
            time.sleep(0.05)
    pending.with_name(pending.name + "-wal").unlink(missing_ok=True)
    pending.with_name(pending.name + "-shm").unlink(missing_ok=True)
    return True


__all__ = [
    "BACKUP_FORMAT_VERSION",
    "ReliabilityError",
    "ReliabilityManager",
    "VaultError",
    "apply_pending_foundation_restore",
    "port_appears_available",
]
