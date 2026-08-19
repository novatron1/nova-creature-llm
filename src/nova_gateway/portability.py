"""Portable, secret-free Nova manifests and ZIP backup validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any
import zipfile

from .config import GatewayConfig
from .comfyui import COMFYUI_ENGINE_VERSION
from .dream_lab import DREAM_LAB_SCHEMA_VERSION
from .engines import ENGINE_INTERFACE_VERSION
from .providers import PROVIDER_INTERFACE_VERSION
from .version import NOVA_VERSION
from .world_model import WORLD_MODEL_SCHEMA_VERSION
from nova_foundation import SCHEMA_VERSION as FOUNDATION_SCHEMA_VERSION


PORTABLE_MANIFEST_VERSION = "1.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass
class NovaPortableManifest:
    manifest_version: str = PORTABLE_MANIFEST_VERSION
    created_at: str = field(default_factory=_now)
    nova_version: str = NOVA_VERSION
    api_version: str = "1.0"
    protocol_version: str = "1.1"
    memory_schema_version: str = "1.0"
    provider_interface_version: str = PROVIDER_INTERFACE_VERSION
    tool_schema_version: str = "1.0"
    capability_schema_version: str = "1.0"
    world_model_schema_version: str = WORLD_MODEL_SCHEMA_VERSION
    dream_lab_schema_version: str = DREAM_LAB_SCHEMA_VERSION
    engine_interface_version: str = ENGINE_INTERFACE_VERSION
    comfyui_engine_version: str = COMFYUI_ENGINE_VERSION
    foundation_schema_version: str = str(FOUNDATION_SCHEMA_VERSION)
    identity_version: str = "existing-nova"
    includes_model_weights: bool = False
    files: dict[str, dict[str, Any]] = field(default_factory=dict)


def model_manifest_from_checkpoint_registry(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    registry_path = root / "checkpoints" / "registry.json"
    if not registry_path.exists():
        return {"schema_version": "1.0", "models": [], "weights_included": False}
    raw = json.loads(registry_path.read_text(encoding="utf-8"))
    models = []
    for role, role_data in (raw.get("roles") or {}).items():
        records = []
        if isinstance(role_data.get("baseline"), dict):
            records.append(role_data["baseline"])
        records.extend(item for item in (role_data.get("candidates") or {}).values() if isinstance(item, dict))
        for record in records:
            path_value = str(record.get("path") or "")
            candidate = Path(path_value)
            local_path = candidate if candidate.is_absolute() else root / candidate
            models.append(
                {
                    "model_identifier": f"nova-checkpoint:{role}:{str(record.get('sha256') or '')[:12]}",
                    "provider": "existing-nova",
                    "file_name": candidate.name,
                    "expected_hash": record.get("sha256"),
                    "size": local_path.stat().st_size if local_path.is_file() else None,
                    "location": "external-model-storage",
                    "download_source": None,
                    "compatibility": {"role": role, "status": record.get("status"), "metrics": record.get("metrics") or {}},
                }
            )
    return {"schema_version": "1.0", "models": models, "weights_included": False}


def export_nova_backup(
    destination: str | Path,
    *,
    project_root: str | Path,
    config: GatewayConfig,
    memory_payload: dict[str, Any],
    tool_metadata: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    model_aliases: list[dict[str, Any]] | None = None,
    conversation_metadata: list[dict[str, Any]] | None = None,
    world_model_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target = Path(destination).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    content: dict[str, bytes] = {
        "config/gateway.json": _json_bytes(config.public_dict()),
        "identity/manifest.json": _json_bytes(
            {
                "identity_id": "nova-creature", "identity_version": "existing-nova",
                "source_modules": ["nova_self_model", "nova_natural_chat", "nova_cognitive_os"],
                "note": "Identity data remains independent from provider model weights.",
            }
        ),
        "memory/memories.json": _json_bytes(memory_payload),
        "tools/registry.json": _json_bytes({"schema_version": "1.0", "tools": tool_metadata}),
        "providers/registry.json": _json_bytes({"schema_version": "1.0", "providers": providers, "credentials_included": False}),
        "conversations/metadata.json": _json_bytes({"schema_version": "1.0", "conversations": conversation_metadata or []}),
        "world_model/checkpoint.json": _json_bytes(
            world_model_payload
            or {
                "schema_version": WORLD_MODEL_SCHEMA_VERSION,
                "privacy": {
                    "prompt_content_stored": False,
                    "response_content_stored": False,
                    "private_chain_of_thought_stored": False,
                    "sensor_values_stored": False,
                },
                "boards": [],
            }
        ),
        "models/manifest.json": _json_bytes(
            {
                **model_manifest_from_checkpoint_registry(project_root),
                "nova_aliases": model_aliases or [],
            }
        ),
        "migrations/versions.json": _json_bytes(
            {
                "configuration": "1.2",
                "protocol": "1.1",
                "memory": "1.0",
                "tools": "1.0",
                "capabilities": "1.0",
                "world_model": WORLD_MODEL_SCHEMA_VERSION,
                "dream_lab": DREAM_LAB_SCHEMA_VERSION,
                "engines": ENGINE_INTERFACE_VERSION,
                "comfyui": COMFYUI_ENGINE_VERSION,
                "foundation": str(FOUNDATION_SCHEMA_VERSION),
            }
        ),
    }
    manifest = NovaPortableManifest()
    manifest.files = {
        name: {"sha256": _sha256_bytes(data), "size": len(data)}
        for name, data in content.items()
    }
    manifest_bytes = _json_bytes(asdict(manifest))
    temporary = target.with_suffix(target.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", manifest_bytes)
        for name, data in content.items():
            archive.writestr(name, data)
    temporary.replace(target)
    return {"ok": True, "path": str(target), "files": len(content) + 1, "bytes": target.stat().st_size, "includes_model_weights": False}


def validate_nova_backup(path: str | Path) -> dict[str, Any]:
    source = Path(path).resolve()
    errors: list[str] = []
    with zipfile.ZipFile(source, "r") as archive:
        names = archive.namelist()
        for name in names:
            parts = PurePosixPath(name).parts
            if name.startswith(("/", "\\")) or ".." in parts:
                errors.append(f"Unsafe archive path: {name}")
        if "manifest.json" not in names:
            return {"ok": False, "path": str(source), "errors": ["manifest.json is missing"]}
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("manifest_version") != PORTABLE_MANIFEST_VERSION:
            errors.append(f"Unsupported manifest version: {manifest.get('manifest_version')!r}")
        if manifest.get("includes_model_weights") is not False:
            errors.append("Portable manifest must explicitly report whether model weights are included.")
        for name, expected in (manifest.get("files") or {}).items():
            if name not in names:
                errors.append(f"Missing file: {name}")
                continue
            data = archive.read(name)
            if _sha256_bytes(data) != expected.get("sha256"):
                errors.append(f"Hash mismatch: {name}")
            if len(data) != expected.get("size"):
                errors.append(f"Size mismatch: {name}")
    return {"ok": not errors, "path": str(source), "errors": errors, "manifest": manifest}


def read_backup_memory(path: str | Path) -> dict[str, Any]:
    validation = validate_nova_backup(path)
    if not validation["ok"]:
        raise ValueError("Nova backup validation failed: " + "; ".join(validation["errors"]))
    with zipfile.ZipFile(Path(path).resolve(), "r") as archive:
        return json.loads(archive.read("memory/memories.json"))


def read_backup_world_model(path: str | Path) -> dict[str, Any]:
    validation = validate_nova_backup(path)
    if not validation["ok"]:
        raise ValueError("Nova backup validation failed: " + "; ".join(validation["errors"]))
    with zipfile.ZipFile(Path(path).resolve(), "r") as archive:
        return json.loads(archive.read("world_model/checkpoint.json"))
