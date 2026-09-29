"""Durable local media custody. Mutations use short, independent transactions."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

from .errors import InvalidRequestError, NovaGatewayError, PermissionDeniedError


class MediaConflictError(NovaGatewayError):
    def __init__(self, message: str):
        super().__init__(message, 'conflict_error', 'media_conflict', 409)


@dataclass(frozen=True)
class AssetRecord:
    id: str
    owner_id: str
    kind: str
    relative_path: str
    sha256: str
    size_bytes: int
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class OutputRecord:
    id: str
    relative_path: str
    sha256: str
    size_bytes: int
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class JobRecord:
    id: str
    owner_id: str
    request_key: str
    request: dict
    stage: str = 'queued'
    backend_id: str | None = None
    external_id: str | None = None
    manifest: dict = field(default_factory=dict)
    error: str | None = None
    cleanup_error: str | None = None
    created_at: str = ''
    updated_at: str = ''


STAGES = ('queued', 'preparing', 'generating_video', 'saving_video',
          'releasing_video', 'preparing_audio', 'exporting', 'verifying', 'completed')
TERMINAL = frozenset(('completed', 'failed', 'cancelled', 'interrupted'))


def _json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':'))
    except (ValueError, TypeError) as exc:
        raise InvalidRequestError('Media data must be finite JSON.') from exc


def _identity(value: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise InvalidRequestError('Media identity must contain 1 to 200 characters.')


class MediaStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise InvalidRequestError('Unsupported media database version.')
            db.execute('CREATE TABLE IF NOT EXISTS media_jobs ('
                       'id TEXT PRIMARY KEY, owner TEXT NOT NULL, request_key TEXT NOT NULL, '
                       'request TEXT NOT NULL, record TEXT NOT NULL, UNIQUE(owner, request_key))')
            db.execute('CREATE TABLE IF NOT EXISTS media_assets ('
                       'id TEXT PRIMARY KEY, owner TEXT NOT NULL, record TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS media_state (key TEXT PRIMARY KEY, value TEXT)')
            db.execute('PRAGMA user_version=1')

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def create_job(self, owner_id: str, request_key: str, request: dict) -> JobRecord:
        _identity(owner_id)
        _identity(request_key)
        if not isinstance(request, dict):
            raise InvalidRequestError('Media request must be an object.')
        encoded = _json(request)
        with self._connection() as db:
            existing = db.execute('SELECT request, record FROM media_jobs WHERE owner=? AND request_key=?',
                                  (owner_id, request_key)).fetchone()
            if existing:
                if existing[0] != encoded:
                    raise MediaConflictError('Request key already belongs to different media settings.')
                return JobRecord(**json.loads(existing[1]))
            now = datetime.now(timezone.utc).isoformat()
            record = JobRecord(uuid4().hex, owner_id, request_key, json.loads(encoded),
                               created_at=now, updated_at=now)
            db.execute('INSERT INTO media_jobs VALUES(?,?,?,?,?)',
                       (record.id, owner_id, request_key, encoded, _json(asdict(record))))
            return record

    def get_job(self, job_id: str, owner_id: str) -> JobRecord:
        with self._connection() as db:
            row = db.execute('SELECT record FROM media_jobs WHERE id=? AND owner=?',
                             (job_id, owner_id)).fetchone()
        if row is None:
            raise PermissionDeniedError('Media job is unavailable to this owner.')
        return JobRecord(**json.loads(row[0]))

    def list_jobs(self, owner_id: str) -> list[JobRecord]:
        with self._connection() as db:
            rows = db.execute('SELECT record FROM media_jobs WHERE owner=? ORDER BY rowid',
                              (owner_id,)).fetchall()
        return [JobRecord(**json.loads(row[0])) for row in rows]

    def transition(self, job_id: str, expected_stage: str, next_stage: str, **fields) -> JobRecord:
        allowed_fields = {'backend_id', 'external_id', 'manifest', 'error', 'cleanup_error'}
        valid_stage = expected_stage in STAGES[:-1]
        next_in_flow = STAGES[STAGES.index(expected_stage) + 1] if valid_stage else None
        if (not valid_stage or next_stage not in {expected_stage, next_in_flow, 'failed', 'cancelled', 'interrupted'}
                or fields.keys() - allowed_fields):
            raise InvalidRequestError('Invalid media transition or immutable field change.')
        with self._connection() as db:
            row = db.execute('SELECT record FROM media_jobs WHERE id=?', (job_id,)).fetchone()
            if not row:
                raise MediaConflictError('Media job no longer exists.')
            record = json.loads(row[0])
            if record['stage'] != expected_stage:
                raise MediaConflictError('Media job stage changed concurrently.')
            for name, value in fields.items():
                # Preserve the first failure; cleanup is a separate diagnostic.
                if name in ('error', 'cleanup_error') and record.get(name):
                    continue
                record[name] = value
            record.update(stage=next_stage, updated_at=datetime.now(timezone.utc).isoformat())
            encoded = _json(record)
            db.execute('UPDATE media_jobs SET record=? WHERE id=?', (encoded, job_id))
            return JobRecord(**json.loads(encoded))

    def register_asset(self, record: AssetRecord) -> None:
        _identity(record.id)
        _identity(record.owner_id)
        if record.kind not in ('image', 'audio'):
            raise InvalidRequestError('Unsupported media asset kind.')
        try:
            with self._connection() as db:
                db.execute('INSERT INTO media_assets VALUES(?,?,?)',
                           (record.id, record.owner_id, _json(asdict(record))))
        except sqlite3.IntegrityError as exc:
            raise MediaConflictError('Media asset is already registered.') from exc

    def get_asset(self, asset_id: str, owner_id: str) -> AssetRecord:
        with self._connection() as db:
            row = db.execute('SELECT record FROM media_assets WHERE id=? AND owner=?',
                             (asset_id, owner_id)).fetchone()
        if row is None:
            raise PermissionDeniedError('Media asset is unavailable to this owner.')
        return AssetRecord(**json.loads(row[0]))

    def set_quarantine(self, reason: str | None) -> None:
        with self._connection() as db:
            db.execute('INSERT INTO media_state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                       ('quarantine', reason))

    def get_quarantine(self) -> str | None:
        with self._connection() as db:
            row = db.execute('SELECT value FROM media_state WHERE key=?', ('quarantine',)).fetchone()
        return row[0] if row else None
