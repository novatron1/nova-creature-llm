from __future__ import annotations

import hashlib
import json
import re
import uuid
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nova_training_types import ROLE_NAMES

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class ResolvedCheckpoint:
    role: str
    path: Path
    sha256: str
    status: str
    metrics: dict


class CheckpointRegistry:
    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.registry_path = self.project_root / "checkpoints" / "registry.json"
        self._data = self._load()

    def register_baseline(self, role: str, path: str | Path, sha256: str) -> None:
        self._validate_role(role)
        self._validate_sha256(sha256)
        resolved_path = self._validate_checkpoint_path(path)
        self._validate_checkpoint_hash(resolved_path, sha256)
        role_record = self._role_record(role)
        previous_baseline = role_record.get("baseline")
        previous_baseline_sha256 = (
            previous_baseline.get("sha256") if isinstance(previous_baseline, dict) else None
        )
        previous_live_sha256 = role_record.get("live_sha256")
        candidates = role_record.setdefault("candidates", {})
        promoted_winner_is_live = (
            isinstance(candidates, dict)
            and isinstance(previous_live_sha256, str)
            and isinstance(candidates.get(previous_live_sha256), dict)
            and candidates[previous_live_sha256].get("status") == "promoted"
        )
        role_record["baseline"] = {
            "path": self._serialize_path(resolved_path),
            "sha256": sha256,
            "status": "baseline",
            "metrics": {},
        }
        if previous_live_sha256 is None or (
            previous_live_sha256 == previous_baseline_sha256 and not promoted_winner_is_live
        ):
            role_record["live_sha256"] = sha256
        self._write()

    def register_candidate(
        self,
        role: str,
        path: str | Path,
        sha256: str,
        metrics: dict[str, Any],
    ) -> None:
        self._validate_role(role)
        self._validate_sha256(sha256)
        resolved_path = self._validate_checkpoint_path(path)
        self._validate_checkpoint_hash(resolved_path, sha256)
        metrics = self._json_safe_dict(metrics, "metrics")
        role_record = self._role_record(role)
        role_record.setdefault("candidates", {})
        role_record["candidates"][sha256] = {
            "path": self._serialize_path(resolved_path),
            "sha256": sha256,
            "status": "candidate",
            "metrics": metrics,
        }
        self._write()

    def promote(self, role: str, candidate_sha256: str) -> None:
        self._validate_role(role)
        self._validate_sha256(candidate_sha256)
        role_record = self._existing_role_record(role)
        candidate = self._candidate_record(role_record, candidate_sha256, role)
        if candidate.get("status") == "rejected":
            raise ValueError(f"candidate is rejected and cannot be promoted: {candidate_sha256!r}")
        previous_winner = role_record.get("live_sha256")
        candidate["status"] = "promoted"
        candidate["rollback_sha256"] = previous_winner
        role_record["live_sha256"] = candidate_sha256
        self._write()

    def reject(self, role: str, candidate_sha256: str, reasons: list[str]) -> None:
        self._validate_role(role)
        self._validate_sha256(candidate_sha256)
        if not isinstance(reasons, list) or not reasons:
            raise ValueError("reasons must be a non-empty list of strings")
        if any(not isinstance(reason, str) or not reason.strip() for reason in reasons):
            raise ValueError("reasons must be a non-empty list of non-blank strings")
        role_record = self._existing_role_record(role)
        candidate = self._candidate_record(role_record, candidate_sha256, role)
        candidate["status"] = "rejected"
        candidate["rejection_reasons"] = list(reasons)
        if role_record.get("live_sha256") == candidate_sha256:
            baseline = role_record.get("baseline")
            role_record["live_sha256"] = baseline.get("sha256") if isinstance(baseline, dict) else None
        self._write()

    def resolve_live(self, role: str) -> ResolvedCheckpoint:
        self._validate_role(role)
        role_record = self._existing_role_record(role)
        baseline = role_record.get("baseline")
        if not isinstance(baseline, dict):
            raise LookupError(f"no baseline registered for role: {role}")

        live_sha256 = role_record.get("live_sha256") or baseline.get("sha256")
        if live_sha256 == baseline.get("sha256"):
            return self._resolved_checkpoint(role, baseline)

        candidate = role_record.get("candidates", {}).get(live_sha256)
        if not isinstance(candidate, dict):
            raise LookupError(f"live checkpoint is missing for role {role}: {live_sha256!r}")
        if candidate.get("status") == "rejected":
            return self._resolved_checkpoint(role, baseline)
        return self._resolved_checkpoint(role, candidate)

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(self._data)

    def _load(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {"version": 1, "roles": {}}
        with self.registry_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict):
            raise ValueError("checkpoint registry must contain a JSON object")
        data.setdefault("version", 1)
        roles = data.setdefault("roles", {})
        if not isinstance(roles, dict):
            raise ValueError("checkpoint registry roles must be a JSON object")
        return data

    def _write(self) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.registry_path.with_name(f"{self.registry_path.name}.{uuid.uuid4().hex}.tmp")
        with tmp_path.open("w", encoding="utf-8") as file:
            json.dump(self._data, file, indent=2, sort_keys=True)
            file.write("\n")
        tmp_path.replace(self.registry_path)

    def _role_record(self, role: str) -> dict[str, Any]:
        roles = self._data.setdefault("roles", {})
        role_record = roles.setdefault(role, {})
        if not isinstance(role_record, dict):
            raise ValueError(f"registry entry for role is invalid: {role!r}")
        return role_record

    def _existing_role_record(self, role: str) -> dict[str, Any]:
        roles = self._data.get("roles", {})
        role_record = roles.get(role)
        if not isinstance(role_record, dict):
            raise LookupError(f"no checkpoints registered for role: {role}")
        return role_record

    def _candidate_record(
        self,
        role_record: dict[str, Any],
        candidate_sha256: str,
        role: str,
    ) -> dict[str, Any]:
        candidates = role_record.get("candidates", {})
        if not isinstance(candidates, dict):
            raise ValueError(f"registry candidates are invalid for role: {role}")
        candidate = candidates.get(candidate_sha256)
        if not isinstance(candidate, dict):
            raise LookupError(f"candidate not registered for role {role}: {candidate_sha256!r}")
        return candidate

    def _resolved_checkpoint(self, role: str, record: dict[str, Any]) -> ResolvedCheckpoint:
        path_value = record.get("path")
        sha256_value = record.get("sha256")
        status_value = record.get("status")
        metrics_value = record.get("metrics", {})
        if not isinstance(path_value, str) or not path_value:
            raise ValueError(f"registry record for {role!r} is missing path")
        if not isinstance(sha256_value, str) or not sha256_value:
            raise ValueError(f"registry record for {role!r} is missing sha256")
        if not isinstance(status_value, str) or not status_value:
            raise ValueError(f"registry record for {role!r} is missing status")
        if not isinstance(metrics_value, dict):
            metrics_value = {}
        resolved_path = self._deserialize_path(path_value)
        self._validate_checkpoint_path(resolved_path, registered=True)
        self._validate_sha256(sha256_value)
        self._validate_checkpoint_hash(resolved_path, sha256_value, registered=True)
        return ResolvedCheckpoint(
            role=role,
            path=resolved_path,
            sha256=sha256_value,
            status=status_value,
            metrics=deepcopy(metrics_value),
        )

    def _serialize_path(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.project_root).as_posix()
        except ValueError:
            return path.resolve().as_posix()

    def _deserialize_path(self, path_value: str) -> Path:
        path = Path(path_value)
        if path.is_absolute():
            return path
        return self.project_root / path

    def _validate_checkpoint_path(self, path: str | Path, registered: bool = False) -> Path:
        resolved_path = Path(path).resolve()
        if not resolved_path.exists():
            if registered:
                raise FileNotFoundError(f"registered checkpoint is missing: {resolved_path}")
            raise FileNotFoundError(f"checkpoint path does not exist: {resolved_path}")
        if not resolved_path.is_file():
            raise ValueError(f"checkpoint path is not a file: {resolved_path}")
        return resolved_path

    def _validate_role(self, role: str) -> None:
        if role not in ROLE_NAMES:
            raise ValueError(f"invalid checkpoint role: {role!r}")

    def _validate_sha256(self, value: str) -> None:
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            raise ValueError("sha256 must be a 64-character hexadecimal string")

    def _validate_checkpoint_hash(
        self,
        path: Path,
        expected_sha256: str,
        registered: bool = False,
    ) -> None:
        actual_sha256 = sha256(path)
        if actual_sha256 != expected_sha256:
            if registered:
                raise ValueError(
                    f"registered checkpoint hash mismatch for {path}: "
                    f"expected {expected_sha256}, got {actual_sha256}"
                )
            raise ValueError(
                f"checkpoint sha256 does not match file for {path}: "
                f"expected {expected_sha256}, got {actual_sha256}"
            )

    def _json_safe_dict(self, value: dict[str, Any], field_name: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError(f"{field_name} must be a dict")
        try:
            return json.loads(json.dumps(value))
        except TypeError as exc:
            raise ValueError(f"{field_name} must be JSON-serializable") from exc


def sha256(path: str | Path) -> str:
    hasher = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
