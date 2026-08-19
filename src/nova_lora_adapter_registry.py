from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import zipfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ADAPTERS_ROOT = ROOT / "models" / "lora_adapters"
DEFAULT_REGISTRY_PATH = DEFAULT_ADAPTERS_ROOT / "registry.json"

REQUIRED_FILES = (
    "adapter_config.json",
    "nova_lora_metadata.json",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", str(text or "").strip().lower()).strip("-")
    return slug or "nova-lora-adapter"


def _safe_extract(archive: zipfile.ZipFile, target_dir: Path) -> None:
    target_root = target_dir.resolve()
    for member in archive.infolist():
        destination = (target_dir / member.filename).resolve()
        if destination != target_root and target_root not in destination.parents:
            raise ValueError(f"Unsafe path in LoRA ZIP: {member.filename}")
    archive.extractall(target_dir)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _validate_extracted_adapter(adapter_dir: Path) -> None:
    missing = [name for name in REQUIRED_FILES if not (adapter_dir / name).exists()]
    has_adapter_model = any(
        (adapter_dir / name).exists()
        for name in ("adapter_model.safetensors", "adapter_model.bin")
    )
    if not has_adapter_model:
        missing.append("adapter_model.safetensors or adapter_model.bin")
    if missing:
        raise ValueError("Missing required LoRA adapter files: " + ", ".join(missing))


def inspect_lora_adapter_zip(zip_path: str | Path) -> dict[str, Any]:
    """Validate a LoRA ZIP and return metadata without installing it."""
    source_zip = Path(zip_path).resolve()
    if not source_zip.exists():
        raise FileNotFoundError(source_zip)
    if not zipfile.is_zipfile(source_zip):
        raise ValueError(f"Not a ZIP file: {source_zip}")
    with tempfile.TemporaryDirectory(prefix="nova_lora_inspect_") as temp_name:
        temp_dir = Path(temp_name)
        with zipfile.ZipFile(source_zip) as archive:
            _safe_extract(archive, temp_dir)
        _validate_extracted_adapter(temp_dir)
        metadata = _read_json(temp_dir / "nova_lora_metadata.json")
        adapter_config = _read_json(temp_dir / "adapter_config.json")
    base_model = str(
        metadata.get("base_model")
        or adapter_config.get("base_model_name_or_path")
        or ""
    )
    return {
        "ok": True,
        "filename": source_zip.name,
        "sha256": _sha256(source_zip),
        "base_model": base_model,
        "train_records": metadata.get("train_records"),
        "validation_records": metadata.get("validation_records"),
        "holdout_records": metadata.get("holdout_records"),
        "epochs": metadata.get("epochs"),
        "eval_metrics": metadata.get("eval_metrics", {}),
    }


def _load_registry(registry_path: Path) -> dict[str, Any]:
    if not registry_path.exists():
        return {"active_adapter_id": None, "adapters": {}}
    payload = _read_json(registry_path)
    if not isinstance(payload.get("adapters"), dict):
        payload["adapters"] = {}
    payload.setdefault("active_adapter_id", None)
    return payload


def import_lora_adapter_zip(
    zip_path: str | Path,
    *,
    adapters_root: str | Path = DEFAULT_ADAPTERS_ROOT,
    registry_path: str | Path | None = None,
    adapter_id: str | None = None,
    activate: bool = True,
) -> dict[str, Any]:
    """Import a trained PEFT/LoRA adapter ZIP into Nova's local adapter registry.

    This does not replace Nova's router, role transformers, checkpoint logic, or
    local LLM choice. It records a trained adapter artifact so a compatible
    Hugging Face/PEFT runtime can load it deliberately.
    """
    source_zip = Path(zip_path).resolve()
    if not source_zip.exists():
        raise FileNotFoundError(source_zip)
    if not zipfile.is_zipfile(source_zip):
        raise ValueError(f"Not a ZIP file: {source_zip}")

    adapters_dir = Path(adapters_root).resolve()
    registry_file = Path(registry_path).resolve() if registry_path else adapters_dir / "registry.json"
    adapters_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="nova_lora_import_") as temp_name:
        temp_dir = Path(temp_name)
        with zipfile.ZipFile(source_zip) as archive:
            _safe_extract(archive, temp_dir)
        _validate_extracted_adapter(temp_dir)

        metadata = _read_json(temp_dir / "nova_lora_metadata.json")
        adapter_config = _read_json(temp_dir / "adapter_config.json")
        base_model = str(
            metadata.get("base_model")
            or adapter_config.get("base_model_name_or_path")
            or ""
        )
        digest = _sha256(source_zip)
        chosen_id = adapter_id or f"{_slug(base_model)}-{digest[:8]}"
        destination = adapters_dir / _slug(chosen_id)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(temp_dir, destination)

    imported = {
        "id": destination.name,
        "path": str(destination),
        "source_zip": str(source_zip),
        "sha256": digest,
        "base_model": base_model,
        "train_records": metadata.get("train_records"),
        "validation_records": metadata.get("validation_records"),
        "holdout_records": metadata.get("holdout_records"),
        "epochs": metadata.get("epochs"),
        "eval_metrics": metadata.get("eval_metrics", {}),
    }

    registry = _load_registry(registry_file)
    registry["adapters"][destination.name] = imported
    if activate:
        registry["active_adapter_id"] = destination.name
    registry_file.parent.mkdir(parents=True, exist_ok=True)
    registry_file.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return imported


def list_lora_adapters(
    *,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
) -> dict[str, Any]:
    """Return all registered adapters with active marker."""
    registry_file = Path(registry_path)
    registry = _load_registry(registry_file)
    active_id = registry.get("active_adapter_id")
    adapters = []
    for adapter_id, adapter in sorted(registry.get("adapters", {}).items()):
        if not isinstance(adapter, dict):
            continue
        path = Path(str(adapter.get("path", "")))
        adapters.append({"id": adapter_id, **adapter, "active": adapter_id == active_id, "exists": path.exists()})
    return {"ok": True, "active_adapter_id": active_id, "adapters": adapters}


def activate_lora_adapter(
    adapter_id: str,
    *,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
) -> dict[str, Any]:
    """Set an already registered adapter as active without deleting old adapters."""
    requested_id = str(adapter_id or "").strip()
    if not requested_id:
        raise ValueError("Missing adapter_id")
    registry_file = Path(registry_path)
    registry = _load_registry(registry_file)
    adapter = registry.get("adapters", {}).get(requested_id)
    if not isinstance(adapter, dict):
        raise FileNotFoundError(f"Adapter not registered: {requested_id}")
    path = Path(str(adapter.get("path", "")))
    if not path.exists():
        raise FileNotFoundError(f"Adapter path not found: {path}")
    registry["active_adapter_id"] = requested_id
    registry_file.parent.mkdir(parents=True, exist_ok=True)
    registry_file.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"id": requested_id, **adapter, "active": True}


def resolve_active_lora_adapter(
    *,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
) -> dict[str, Any] | None:
    registry_file = Path(registry_path)
    registry = _load_registry(registry_file)
    active_id = registry.get("active_adapter_id")
    if not active_id:
        return None
    adapter = registry.get("adapters", {}).get(str(active_id))
    if not isinstance(adapter, dict):
        return None
    path = Path(str(adapter.get("path", "")))
    if not path.exists():
        return None
    return {"id": str(active_id), **adapter}


def resolve_lora_adapter(
    adapter_id: str,
    *,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
) -> dict[str, Any] | None:
    """Resolve one registered adapter by id without changing the active adapter."""
    requested_id = str(adapter_id or "").strip()
    if not requested_id:
        return None
    registry_file = Path(registry_path)
    registry = _load_registry(registry_file)
    adapter = registry.get("adapters", {}).get(requested_id)
    if not isinstance(adapter, dict):
        return None
    path = Path(str(adapter.get("path", "")))
    if not path.exists():
        return None
    return {"id": requested_id, **adapter}
