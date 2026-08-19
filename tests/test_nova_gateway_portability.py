from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_gateway.config import GatewayConfig  # noqa: E402
from nova_gateway.engines import NovaEngineRegistry, NovaVisionEngine  # noqa: E402
from nova_gateway.errors import ProviderUnavailableError, UnsupportedFeatureError  # noqa: E402
from nova_gateway.mcp import NovaMcpExtensionBoundary  # noqa: E402
from nova_gateway.portability import (  # noqa: E402
    export_nova_backup,
    read_backup_memory,
    read_backup_world_model,
    validate_nova_backup,
)


def test_portable_backup_excludes_secrets_and_weights_and_validates_hashes(tmp_path: Path) -> None:
    destination = tmp_path / "nova-portable.zip"
    config = GatewayConfig(client_registry_path=tmp_path / "secret-clients.json")
    memory = {"schema_version": "1.0", "records": [{"memory_id": "mem_1", "content": "portable fact"}]}
    result = export_nova_backup(
        destination,
        project_root=tmp_path,
        config=config,
        memory_payload=memory,
        tool_metadata=[{"name": "memory_search", "schema_version": "1.0"}],
        providers=[{"provider_id": "existing-nova", "credentials_included": False}],
        model_aliases=[{"id": "nova", "provider_id": "existing-nova"}],
    )

    assert result["ok"] is True
    assert result["includes_model_weights"] is False
    validation = validate_nova_backup(destination)
    assert validation["ok"] is True
    assert validation["manifest"]["includes_model_weights"] is False
    assert validation["manifest"]["foundation_schema_version"] == "2"
    assert read_backup_memory(destination) == memory
    with zipfile.ZipFile(destination) as archive:
        names = archive.namelist()
        assert not any(name.endswith((".pt", ".bin", ".safetensors", ".gguf")) for name in names)
        assert "world_model/checkpoint.json" in names
        raw = b"".join(archive.read(name) for name in names)
        assert b"secret-clients" not in raw
    world_model = read_backup_world_model(destination)
    assert world_model["boards"] == []
    assert world_model["privacy"]["private_chain_of_thought_stored"] is False


def test_backup_tampering_is_detected(tmp_path: Path) -> None:
    original = tmp_path / "original.zip"
    export_nova_backup(
        original,
        project_root=tmp_path,
        config=GatewayConfig(),
        memory_payload={"schema_version": "1.0", "records": []},
        tool_metadata=[],
        providers=[],
    )
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(original, "r") as source, zipfile.ZipFile(tampered, "w") as target:
        for name in source.namelist():
            data = source.read(name)
            if name == "memory/memories.json":
                data = b'{"tampered":true}'
            target.writestr(name, data)
    validation = validate_nova_backup(tampered)
    assert validation["ok"] is False
    assert any("Hash mismatch" in error or "Size mismatch" in error for error in validation["errors"])


class HealthyVisionEngine(NovaVisionEngine):
    engine_id = "test-vision"

    def health_check(self):
        return {"ok": True}

    def analyze_image(self, image, **options):
        return {"objects": []}

    def describe_image(self, image, **options):
        return "test image"

    def extract_visual_features(self, image, **options):
        return {"features": []}


class UnhealthyVisionEngine(HealthyVisionEngine):
    engine_id = "bad-vision"

    def health_check(self):
        return {"ok": False}


def test_engine_registry_requires_real_healthy_implementation() -> None:
    registry = NovaEngineRegistry()
    registry.register(HealthyVisionEngine())
    assert registry.get("test-vision").describe_image(None) == "test image"
    assert registry.list()[0]["engine_type"] == "vision"
    with pytest.raises(ProviderUnavailableError):
        registry.register(UnhealthyVisionEngine())


def test_mcp_boundary_never_claims_unimplemented_runtime_success() -> None:
    boundary = NovaMcpExtensionBoundary()
    assert boundary.status()["client"] == "NOT IMPLEMENTED"
    assert boundary.status()["server"] == "NOT IMPLEMENTED"
    with pytest.raises(UnsupportedFeatureError):
        boundary.connect_server({})
    with pytest.raises(UnsupportedFeatureError):
        boundary.serve({})


def test_cli_doctor_and_migrate_are_non_mutating(tmp_path: Path) -> None:
    environment = {
        "NOVA_CLIENT_REGISTRY_PATH": str(tmp_path / "clients.json"),
        "NOVA_MEMORY_MODE": "read_only",
        "NOVA_WORLD_MODEL_PATH": str(tmp_path / "restored-world-model.json"),
    }
    import os
    full_env = dict(os.environ)
    full_env.update(environment)
    doctor = subprocess.run(
        [sys.executable, str(ROOT / "nova_cli.py"), "doctor"], cwd=ROOT, env=full_env,
        capture_output=True, text=True, timeout=30,
    )
    assert doctor.returncode == 0
    assert json.loads(doctor.stdout)["gateway"]["memory_mode"] == "read_only"
    assert json.loads(doctor.stdout)["world_model"]["persistence"] == "versioned_local_checkpoint"
    migrate = subprocess.run(
        [sys.executable, str(ROOT / "nova_cli.py"), "migrate"], cwd=ROOT, env=full_env,
        capture_output=True, text=True, timeout=30,
    )
    assert migrate.returncode == 0
    assert json.loads(migrate.stdout)["changes_applied"] == 0
    assert json.loads(migrate.stdout)["versions"]["foundation"] == "2"

    portable = tmp_path / "world-model-portable.zip"
    export_nova_backup(
        portable,
        project_root=tmp_path,
        config=GatewayConfig(),
        memory_payload={"schema_version": "1.0", "records": []},
        tool_metadata=[],
        providers=[],
        world_model_payload={
            "schema_version": "1.1",
            "boards": [
                {
                    "client_id": "portable_phone",
                    "conversation_id": "portable_conversation",
                    "current_topic": "coding",
                    "active_goal": "Answer the user's current question",
                    "turn_count": 3,
                }
            ],
        },
    )
    restore = subprocess.run(
        [
            sys.executable,
            str(ROOT / "nova_cli.py"),
            "import",
            str(portable),
            "--apply-world-model",
        ],
        cwd=ROOT,
        env=full_env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    restored = json.loads(
        (tmp_path / "restored-world-model.json").read_text(encoding="utf-8")
    )
    assert restore.returncode == 0, restore.stderr
    assert json.loads(restore.stdout)["world_model_records_imported"] == 1
    assert restored["boards"][0]["conversation_id"] == "portable_conversation"
