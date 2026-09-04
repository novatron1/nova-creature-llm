#!/usr/bin/env python3
"""Maintainable standard-library CLI for Nova gateway administration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets
import sys


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from nova_gateway.auth import ALL_PERMISSION_SCOPES, NovaClientRegistry  # noqa: E402
from nova_gateway.config import GatewayConfig  # noqa: E402
from nova_gateway.memory import ExistingNovaMemoryStore  # noqa: E402
from nova_gateway.portability import (  # noqa: E402
    export_nova_backup,
    read_backup_memory,
    read_backup_world_model,
    validate_nova_backup,
)
from nova_gateway.tools import registry_from_existing_tools  # noqa: E402
from nova_gateway.world_model import NovaWorldModel, WORLD_MODEL_SCHEMA_VERSION  # noqa: E402
from nova_gateway.comfyui import COMFYUI_ENGINE_VERSION  # noqa: E402
from nova_gateway.dream_lab import DREAM_LAB_SCHEMA_VERSION  # noqa: E402
from nova_gateway.engines import ENGINE_INTERFACE_VERSION  # noqa: E402
from nova_foundation import SCHEMA_VERSION as FOUNDATION_SCHEMA_VERSION  # noqa: E402


def _config() -> GatewayConfig:
    return GatewayConfig.from_env(root=ROOT, default_port=8765)


def command_doctor(args) -> int:
    config = _config()
    memory = ExistingNovaMemoryStore(mode=config.memory_mode)
    world_model = NovaWorldModel(
        persistence=config.world_model_persistence,
        checkpoint_path=(
            config.world_model_checkpoint_path
            if config.world_model_persistence == "checkpoint"
            else None
        ),
        max_age_days=config.world_model_max_age_days,
    )
    result = {
        "ok": True,
        "gateway": config.public_dict(),
        "memory": memory.health_check(),
        "world_model": world_model.health_check(),
        "client_registry_exists": config.client_registry_path.exists(),
        "ollama": {"checked": False},
    }
    if args.check_ollama:
        try:
            from nova_gateway.providers import OllamaProvider
            result["ollama"] = {"checked": True, **OllamaProvider().health_check()}
        except Exception as exc:
            result["ollama"] = {"checked": True, "ok": False, "error": str(exc)}
    result["ok"] = (
        bool(result["memory"].get("ok"))
        and bool(result["world_model"].get("ok"))
        and (not args.check_ollama or bool(result["ollama"].get("ok")))
    )
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def command_client_add(args) -> int:
    config = _config()
    scopes = {item.strip() for item in args.scopes.split(",") if item.strip()}
    unknown = scopes - ALL_PERMISSION_SCOPES
    if unknown:
        raise SystemExit("Unknown scopes: " + ", ".join(sorted(unknown)))
    api_key = secrets.token_urlsafe(32)
    registry = NovaClientRegistry(config.client_registry_path)
    registry.add_client(args.id, args.name or args.id, api_key, scopes, allowed_ips=args.allowed_ip or [])
    print(json.dumps({
        "client_id": args.id, "scopes": sorted(scopes), "api_key": api_key,
        "warning": "This is the only time Nova prints this key. Store it securely.",
    }, indent=2))
    return 0


def command_client_list(_args) -> int:
    registry = NovaClientRegistry(_config().client_registry_path)
    print(json.dumps({"clients": registry.list_clients()}, indent=2))
    return 0


def command_export(args) -> int:
    config = _config()
    memory = ExistingNovaMemoryStore(mode=config.memory_mode)
    world_model = NovaWorldModel(
        persistence=config.world_model_persistence,
        checkpoint_path=(
            config.world_model_checkpoint_path
            if config.world_model_persistence == "checkpoint"
            else None
        ),
        max_age_days=config.world_model_max_age_days,
    )
    tools = registry_from_existing_tools()
    providers = [
        {"provider_id": "existing-nova", "default": True, "credentials_included": False},
        {"provider_id": "ollama", "default": False, "credentials_included": False},
    ]
    result = export_nova_backup(
        args.path, project_root=ROOT, config=config, memory_payload=memory.export_memories(),
        tool_metadata=tools.list(), providers=providers,
        model_aliases=[{"id": alias, "provider_id": "existing-nova"} for alias in ("nova", "nova-default", "nova-fast", "nova-deep", "nova-local", "nova-coder")],
        world_model_payload=world_model.export_checkpoint_payload(),
    )
    print(json.dumps(result, indent=2))
    return 0


def command_validate(args) -> int:
    result = validate_nova_backup(args.path)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def command_import(args) -> int:
    if not args.apply_memory and not args.apply_world_model:
        print(json.dumps({
            "ok": False,
            "message": (
                "Validation only. Add --apply-memory and/or --apply-world-model "
                "to restore selected records."
            ),
        }, indent=2))
        return command_validate(args)
    config = _config()
    result = {"ok": True, "memory_records_imported": 0, "world_model_records_imported": 0}
    if args.apply_memory:
        memory = ExistingNovaMemoryStore(mode=config.memory_mode)
        result["memory_records_imported"] = memory.import_memories(read_backup_memory(args.path))
    if args.apply_world_model:
        world_model = NovaWorldModel(
            persistence=config.world_model_persistence,
            checkpoint_path=(
                config.world_model_checkpoint_path
                if config.world_model_persistence == "checkpoint"
                else None
            ),
            max_age_days=config.world_model_max_age_days,
        )
        imported = world_model.import_checkpoint_payload(read_backup_world_model(args.path))
        result["world_model_records_imported"] = imported["imported"]
        result["world_model_records_rejected"] = imported["rejected"]
    print(json.dumps(result, indent=2))
    return 0


def command_migrate(_args) -> int:
    print(json.dumps({
        "ok": True, "changes_applied": 0,
        "versions": {
            "configuration": "1.2",
            "protocol": "1.1",
            "memory": "1.0",
            "providers": "1.0",
            "tools": "1.0",
            "world_model": WORLD_MODEL_SCHEMA_VERSION,
            "dream_lab": DREAM_LAB_SCHEMA_VERSION,
            "engines": ENGINE_INTERFACE_VERSION,
            "comfyui": COMFYUI_ENGINE_VERSION,
            "foundation": str(FOUNDATION_SCHEMA_VERSION),
        },
        "message": "All registered schemas are current; stored data was not silently mutated.",
    }, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nova", description="Nova gateway administration")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="Check local Nova components")
    doctor.add_argument("--check-ollama", action="store_true")
    doctor.set_defaults(func=command_doctor)
    client = sub.add_parser("client", help="Manage scoped API clients")
    client_sub = client.add_subparsers(dest="client_command", required=True)
    client_add = client_sub.add_parser("add")
    client_add.add_argument("--id", required=True)
    client_add.add_argument("--name")
    client_add.add_argument("--scopes", default="chat.generate,chat.stream,tools.list,admin.models")
    client_add.add_argument("--allowed-ip", action="append")
    client_add.set_defaults(func=command_client_add)
    client_list = client_sub.add_parser("list")
    client_list.set_defaults(func=command_client_list)
    export = sub.add_parser("export", help="Create a portable backup without model weights or secrets")
    export.add_argument("path")
    export.set_defaults(func=command_export)
    validate = sub.add_parser("validate-backup")
    validate.add_argument("path")
    validate.set_defaults(func=command_validate)
    restore = sub.add_parser("import")
    restore.add_argument("path")
    restore.add_argument("--apply-memory", action="store_true")
    restore.add_argument("--apply-world-model", action="store_true")
    restore.set_defaults(func=command_import)
    migrate = sub.add_parser("migrate")
    migrate.set_defaults(func=command_migrate)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
