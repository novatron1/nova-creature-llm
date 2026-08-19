"""Durable security and background-work foundations for Nova.

This module intentionally uses only the Python standard library. It provides:

* a small, migrated SQLite store with WAL enabled;
* one-time pairing codes and hashed device tokens;
* durable, observable background jobs with cooperative cancellation; and
* a compact audit trail for security-sensitive actions.

Raw pairing codes and bearer tokens are never persisted.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import queue
import secrets
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


SCHEMA_VERSION = 2
TERMINAL_JOB_STATUSES = {"succeeded", "failed", "cancelled"}
DEVICE_OPTIONAL_SCOPES = frozenset({"image.generate", "video.generate"})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime | None = None) -> str:
    return (value or _utc_now()).isoformat(timespec="milliseconds")


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _json_load(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _secret_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pairing_code_hash(session_id: str, code: str) -> str:
    return _secret_hash(f"{session_id}:{code}")


def _clean_device_name(name: Any) -> str:
    value = " ".join(str(name or "Nova device").split()).strip()
    return value[:80] or "Nova device"


class FoundationError(RuntimeError):
    """Base error for expected foundation failures."""


class PairingError(FoundationError):
    """Raised when a pairing code or device token is invalid."""


class JobError(FoundationError):
    """Raised when a job request is invalid."""


class FoundationStore:
    """Thread-safe, connection-per-operation SQLite persistence."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path).expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._schema_lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.database_path), timeout=10.0, isolation_level=None
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._schema_lock, self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            try:
                connection.executescript(
                    """
                    BEGIN IMMEDIATE;

                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        applied_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS pairing_sessions (
                        id TEXT PRIMARY KEY,
                        code_hash TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        used_at TEXT
                    );
                    CREATE INDEX IF NOT EXISTS pairing_sessions_active_idx
                        ON pairing_sessions(expires_at, used_at);

                    CREATE TABLE IF NOT EXISTS paired_devices (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        token_hash TEXT NOT NULL UNIQUE,
                        user_agent TEXT,
                        scopes_json TEXT NOT NULL DEFAULT '[]',
                        created_at TEXT NOT NULL,
                        last_seen_at TEXT,
                        revoked_at TEXT
                    );
                    CREATE INDEX IF NOT EXISTS paired_devices_active_idx
                        ON paired_devices(revoked_at, created_at);

                    CREATE TABLE IF NOT EXISTS jobs (
                        id TEXT PRIMARY KEY,
                        kind TEXT NOT NULL,
                        status TEXT NOT NULL,
                        progress INTEGER NOT NULL DEFAULT 0,
                        message TEXT NOT NULL DEFAULT '',
                        payload_json TEXT NOT NULL DEFAULT '{}',
                        result_json TEXT,
                        error TEXT,
                        created_at TEXT NOT NULL,
                        started_at TEXT,
                        finished_at TEXT,
                        cancel_requested INTEGER NOT NULL DEFAULT 0
                    );
                    CREATE INDEX IF NOT EXISTS jobs_created_idx
                        ON jobs(created_at DESC);
                    CREATE INDEX IF NOT EXISTS jobs_status_idx
                        ON jobs(status, created_at);

                    CREATE TABLE IF NOT EXISTS audit_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_type TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        detail_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS audit_events_created_idx
                        ON audit_events(created_at DESC);
                    """
                )
                paired_columns = {
                    str(row["name"])
                    for row in connection.execute("PRAGMA table_info(paired_devices)").fetchall()
                }
                if "scopes_json" not in paired_columns:
                    connection.execute(
                        "ALTER TABLE paired_devices "
                        "ADD COLUMN scopes_json TEXT NOT NULL DEFAULT '[]'"
                    )
                connection.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, _timestamp()),
                )
                connection.execute("COMMIT")
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    def health(self) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute("SELECT 1").fetchone()
            row = connection.execute(
                "SELECT MAX(version) AS version FROM schema_migrations"
            ).fetchone()
            journal = connection.execute("PRAGMA journal_mode").fetchone()[0]
        return {
            "ok": True,
            "schema_version": int(row["version"] or 0),
            "journal_mode": str(journal).lower(),
            "database": str(self.database_path),
        }

    def record_audit(
        self, event_type: str, *, actor: str = "system", detail: Mapping[str, Any] | None = None
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO audit_events(event_type, actor, detail_json, created_at) VALUES (?, ?, ?, ?)",
                (str(event_type)[:80], str(actor)[:120], _json_dump(dict(detail or {})), _timestamp()),
            )

    def recent_audit_events(self, limit: int = 50) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 500))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (safe_limit,)
            ).fetchall()
        return [
            {
                "id": row["id"],
                "event_type": row["event_type"],
                "actor": row["actor"],
                "detail": _json_load(row["detail_json"], {}),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def create_pairing_session(self, ttl_seconds: int = 300) -> dict[str, Any]:
        ttl = max(30, min(int(ttl_seconds), 1800))
        session_id = uuid.uuid4().hex
        code = f"{secrets.randbelow(1_000_000):06d}"
        created = _utc_now()
        expires = created + timedelta(seconds=ttl)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "DELETE FROM pairing_sessions WHERE expires_at < ? OR used_at IS NOT NULL",
                    (_timestamp(created),),
                )
                connection.execute(
                    """INSERT INTO pairing_sessions
                       (id, code_hash, created_at, expires_at, used_at)
                       VALUES (?, ?, ?, ?, NULL)""",
                    (
                        session_id,
                        _pairing_code_hash(session_id, code),
                        _timestamp(created),
                        _timestamp(expires),
                    ),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        self.record_audit("pairing_session_created", detail={"session_id": session_id})
        return {
            "session_id": session_id,
            "code": code,
            "created_at": _timestamp(created),
            "expires_at": _timestamp(expires),
            "ttl_seconds": ttl,
        }

    def exchange_pairing_code(
        self, code: str, device_name: Any, *, user_agent: str | None = None
    ) -> dict[str, Any]:
        normalized_code = "".join(character for character in str(code or "") if character.isdigit())
        if len(normalized_code) != 6:
            raise PairingError("Pairing code must contain six digits.")

        now = _timestamp()
        device_id = uuid.uuid4().hex
        token = f"nova_{secrets.token_urlsafe(32)}"
        token_hash = _secret_hash(token)
        name = _clean_device_name(device_name)
        matched_session: str | None = None

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                sessions = connection.execute(
                    """SELECT id, code_hash FROM pairing_sessions
                       WHERE used_at IS NULL AND expires_at >= ?
                       ORDER BY created_at DESC""",
                    (now,),
                ).fetchall()
                for session in sessions:
                    candidate = _pairing_code_hash(session["id"], normalized_code)
                    if hmac.compare_digest(candidate, session["code_hash"]):
                        matched_session = session["id"]
                        break
                if not matched_session:
                    raise PairingError("That pairing code is invalid or has expired.")
                updated = connection.execute(
                    "UPDATE pairing_sessions SET used_at = ? WHERE id = ? AND used_at IS NULL",
                    (now, matched_session),
                )
                if updated.rowcount != 1:
                    raise PairingError("That pairing code has already been used.")
                connection.execute(
                    """INSERT INTO paired_devices
                       (id, name, token_hash, user_agent, scopes_json,
                        created_at, last_seen_at, revoked_at)
                       VALUES (?, ?, ?, ?, '[]', ?, ?, NULL)""",
                    (device_id, name, token_hash, str(user_agent or "")[:500], now, now),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

        self.record_audit(
            "device_paired", actor=device_id, detail={"device_id": device_id, "name": name}
        )
        return {
            "token": token,
            "device": {
                "id": device_id,
                "name": name,
                "created_at": now,
                "last_seen_at": now,
                "revoked_at": None,
            },
        }

    def validate_device_token(self, token: str, *, touch: bool = True) -> dict[str, Any] | None:
        candidate = str(token or "").strip()
        if not candidate.startswith("nova_") or len(candidate) < 24:
            return None
        token_hash = _secret_hash(candidate)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM paired_devices WHERE token_hash = ? AND revoked_at IS NULL",
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            last_seen = row["last_seen_at"]
            should_touch = bool(touch)
            if should_touch and last_seen:
                try:
                    should_touch = (_utc_now() - datetime.fromisoformat(last_seen)).total_seconds() >= 60
                except (TypeError, ValueError):
                    should_touch = True
            if should_touch:
                last_seen = _timestamp()
                connection.execute(
                    "UPDATE paired_devices SET last_seen_at = ? WHERE id = ?",
                    (last_seen, row["id"]),
                )
        return {
            "id": row["id"],
            "name": row["name"],
            "scopes": self._device_scopes(row["scopes_json"]),
            "created_at": row["created_at"],
            "last_seen_at": last_seen,
            "revoked_at": row["revoked_at"],
        }

    def list_paired_devices(self, *, include_revoked: bool = False) -> list[dict[str, Any]]:
        where = "" if include_revoked else "WHERE revoked_at IS NULL"
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT id, name, user_agent, scopes_json,
                           created_at, last_seen_at, revoked_at
                    FROM paired_devices {where} ORDER BY created_at DESC"""
            ).fetchall()
        return [
            {
                **{key: row[key] for key in row.keys() if key != "scopes_json"},
                "scopes": self._device_scopes(row["scopes_json"]),
            }
            for row in rows
        ]

    @staticmethod
    def _device_scopes(value: Any) -> list[str]:
        parsed = _json_load(value, [])
        if not isinstance(parsed, list):
            return []
        return sorted(
            {
                str(scope)
                for scope in parsed
                if str(scope) in DEVICE_OPTIONAL_SCOPES
            }
        )

    def set_device_scopes(self, device_id: str, scopes: Any) -> list[str]:
        if not isinstance(scopes, (list, tuple, set, frozenset)):
            raise PairingError("Device scopes must be a list.")
        requested = {str(scope).strip() for scope in scopes if str(scope).strip()}
        unknown = requested - DEVICE_OPTIONAL_SCOPES
        if unknown:
            raise PairingError(
                "Unsupported device scopes: " + ", ".join(sorted(unknown))
            )
        normalized = sorted(requested)
        with self._connect() as connection:
            result = connection.execute(
                """UPDATE paired_devices SET scopes_json = ?
                   WHERE id = ? AND revoked_at IS NULL""",
                (_json_dump(normalized), str(device_id)),
            )
        if result.rowcount != 1:
            raise PairingError("Paired device was not found.")
        self.record_audit(
            "device_scopes_updated",
            actor=str(device_id),
            detail={"device_id": str(device_id), "scopes": normalized},
        )
        return normalized

    def paired_device_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM paired_devices WHERE revoked_at IS NULL"
            ).fetchone()
        return int(row["count"])

    def revoke_device(self, device_id: str) -> bool:
        now = _timestamp()
        with self._connect() as connection:
            result = connection.execute(
                "UPDATE paired_devices SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (now, str(device_id)),
            )
        changed = result.rowcount == 1
        if changed:
            self.record_audit("device_revoked", actor=str(device_id), detail={"device_id": device_id})
        return changed

    def create_job(self, kind: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        created_at = _timestamp()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO jobs
                   (id, kind, status, progress, message, payload_json, created_at, cancel_requested)
                   VALUES (?, ?, 'queued', 0, 'Queued', ?, ?, 0)""",
                (job_id, str(kind)[:100], _json_dump(dict(payload or {})), created_at),
            )
        self.record_audit("job_created", actor=job_id, detail={"job_id": job_id, "kind": kind})
        return self.get_job(job_id) or {}

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: int | None = None,
        message: str | None = None,
        result: Any = None,
        error: str | None = None,
        set_result: bool = False,
    ) -> dict[str, Any]:
        assignments: list[str] = []
        values: list[Any] = []
        if status is not None:
            assignments.append("status = ?")
            values.append(status)
            if status == "running":
                assignments.append("started_at = COALESCE(started_at, ?)")
                values.append(_timestamp())
            if status in TERMINAL_JOB_STATUSES:
                assignments.append("finished_at = ?")
                values.append(_timestamp())
        if progress is not None:
            assignments.append("progress = ?")
            values.append(max(0, min(int(progress), 100)))
        if message is not None:
            assignments.append("message = ?")
            values.append(str(message)[:500])
        if set_result:
            assignments.append("result_json = ?")
            values.append(_json_dump(result))
        if error is not None:
            assignments.append("error = ?")
            values.append(str(error)[:4000])
        if not assignments:
            return self.get_job(job_id) or {}
        values.append(str(job_id))
        with self._connect() as connection:
            connection.execute(
                f"UPDATE jobs SET {', '.join(assignments)} WHERE id = ?", values
            )
        job = self.get_job(job_id)
        if job is None:
            raise JobError("Job not found.")
        return job

    def request_job_cancel(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            result = connection.execute(
                """UPDATE jobs SET cancel_requested = 1, message = 'Cancellation requested'
                   WHERE id = ? AND status IN ('queued', 'running')""",
                (str(job_id),),
            )
        if result.rowcount:
            self.record_audit("job_cancel_requested", actor=str(job_id), detail={"job_id": job_id})
        return self.get_job(job_id)

    def is_job_cancel_requested(self, job_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT cancel_requested FROM jobs WHERE id = ?", (str(job_id),)
            ).fetchone()
        return bool(row and row["cancel_requested"])

    def recover_interrupted_jobs(self) -> int:
        now = _timestamp()
        with self._connect() as connection:
            result = connection.execute(
                """UPDATE jobs
                   SET status = 'failed', progress = CASE WHEN progress > 99 THEN 99 ELSE progress END,
                       message = 'Interrupted by application restart',
                       error = 'The application restarted before this job completed.',
                       finished_at = ?
                   WHERE status IN ('queued', 'running')""",
                (now,),
            )
        if result.rowcount:
            self.record_audit(
                "jobs_recovered", detail={"interrupted_jobs": int(result.rowcount)}
            )
        return int(result.rowcount)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (str(job_id),)).fetchone()
        return self._job_from_row(row) if row else None

    def find_active_job(self, kind: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT * FROM jobs
                   WHERE kind = ? AND status IN ('queued', 'running')
                   ORDER BY created_at ASC LIMIT 1""",
                (str(kind),),
            ).fetchone()
        return self._job_from_row(row) if row else None

    def list_jobs(self, limit: int = 25) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 200))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (safe_limit,)
            ).fetchall()
        return [self._job_from_row(row) for row in rows]

    @staticmethod
    def _job_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "kind": row["kind"],
            "status": row["status"],
            "progress": int(row["progress"]),
            "message": row["message"],
            "payload": _json_load(row["payload_json"], {}),
            "result": _json_load(row["result_json"], None),
            "error": row["error"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "cancel_requested": bool(row["cancel_requested"]),
        }


@dataclass(frozen=True)
class JobContext:
    store: FoundationStore
    job_id: str

    def update(self, progress: int, message: str) -> dict[str, Any]:
        return self.store.update_job(self.job_id, progress=progress, message=message)

    def cancelled(self) -> bool:
        return self.store.is_job_cancel_requested(self.job_id)

    def raise_if_cancelled(self) -> None:
        if self.cancelled():
            raise JobCancelled("Job cancelled.")


class JobCancelled(JobError):
    """Raised by a cooperative job when cancellation is requested."""


JobHandler = Callable[[JobContext, Mapping[str, Any]], Any]


class PersistentJobRunner:
    """A bounded daemon-worker job runner backed by :class:`FoundationStore`."""

    def __init__(self, store: FoundationStore, max_workers: int = 1):
        self.store = store
        self.max_workers = max(1, min(int(max_workers), 4))
        self._handlers: dict[str, JobHandler] = {}
        self._start_lock = threading.Lock()
        self._queue: queue.Queue[tuple[str, str, dict[str, Any]] | None] = queue.Queue()
        self._workers: list[threading.Thread] = []
        self.store.recover_interrupted_jobs()
        for index in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"nova-foundation-worker-{index + 1}",
                daemon=True,
            )
            worker.start()
            self._workers.append(worker)

    def register(self, kind: str, handler: JobHandler) -> None:
        if not callable(handler):
            raise TypeError("Job handler must be callable.")
        self._handlers[str(kind)] = handler

    def start(self, kind: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        normalized_kind = str(kind)
        if normalized_kind not in self._handlers:
            raise JobError(f"Unsupported job kind: {normalized_kind}")
        safe_payload = dict(payload or {})
        with self._start_lock:
            active = self.store.find_active_job(normalized_kind)
            if active is not None:
                return {**active, "deduplicated": True}
            job = self.store.create_job(normalized_kind, safe_payload)
            self._queue.put((job["id"], normalized_kind, safe_payload))
        return job

    def cancel(self, job_id: str) -> dict[str, Any]:
        job = self.store.request_job_cancel(job_id)
        if job is None:
            raise JobError("Job not found.")
        return job

    def _worker_loop(self) -> None:
        while True:
            work = self._queue.get()
            if work is None:
                self._queue.task_done()
                return
            job_id, kind, payload = work
            try:
                self._run_job(job_id, kind, payload)
            finally:
                self._queue.task_done()

    def _run_job(self, job_id: str, kind: str, payload: Mapping[str, Any]) -> None:
        context = JobContext(self.store, job_id)
        if context.cancelled():
            self.store.update_job(
                job_id, status="cancelled", message="Cancelled before starting"
            )
            return
        handler = self._handlers.get(kind)
        if handler is None:
            self.store.update_job(
                job_id,
                status="failed",
                message="Job handler unavailable",
                error=f"No handler is registered for {kind}.",
            )
            return
        self.store.update_job(job_id, status="running", progress=1, message="Starting")
        try:
            result = handler(context, payload)
            if context.cancelled():
                self.store.update_job(
                    job_id, status="cancelled", message="Cancelled", set_result=True, result=result
                )
            else:
                self.store.update_job(
                    job_id,
                    status="succeeded",
                    progress=100,
                    message="Completed",
                    set_result=True,
                    result=result,
                )
                self.store.record_audit(
                    "job_succeeded", actor=job_id, detail={"job_id": job_id, "kind": kind}
                )
        except JobCancelled:
            self.store.update_job(job_id, status="cancelled", message="Cancelled")
        except Exception as exc:  # The job boundary must preserve failure state.
            self.store.update_job(
                job_id,
                status="failed",
                message="Failed",
                error=f"{type(exc).__name__}: {exc}",
            )
            self.store.record_audit(
                "job_failed",
                actor=job_id,
                detail={"job_id": job_id, "kind": kind, "error_type": type(exc).__name__},
            )


class NovaFoundation:
    """Facade used by the web server."""

    def __init__(self, database_path: str | Path, *, max_workers: int = 1):
        self.store = FoundationStore(database_path)
        self.jobs = PersistentJobRunner(self.store, max_workers=max_workers)

    def health(self) -> dict[str, Any]:
        result = self.store.health()
        result.update(
            {
                "paired_devices": self.store.paired_device_count(),
                "recent_jobs": len(self.store.list_jobs(limit=25)),
            }
        )
        return result


def create_foundation(root: str | Path, *, max_workers: int = 1) -> NovaFoundation:
    root_path = Path(root).expanduser().resolve()
    return NovaFoundation(root_path / "data" / "nova_foundation.db", max_workers=max_workers)


__all__ = [
    "FoundationError",
    "FoundationStore",
    "JobCancelled",
    "JobContext",
    "JobError",
    "NovaFoundation",
    "PairingError",
    "PersistentJobRunner",
    "SCHEMA_VERSION",
    "create_foundation",
]
