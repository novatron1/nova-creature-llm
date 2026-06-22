from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from nova_checkpoint_registry import CheckpointRegistry, sha256
from nova_training_types import ROLE_NAMES


def run_preflight(
    project_root: str | Path,
    required_roles: Sequence[str] = ROLE_NAMES,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    checks = {
        "python": sys.version_info >= (3, 11),
        "torch": importlib.util.find_spec("torch") is not None,
        "pytest": importlib.util.find_spec("pytest") is not None,
    }
    runtime = {
        "python": sys.version.split()[0],
        "torch": _package_version("torch"),
        "pytest": _package_version("pytest"),
    }
    reasons: list[str] = []
    hashes: dict[str, str | None] = {}
    role_evidence: dict[str, dict[str, Any]] = {}
    roles_ready = 0

    for name, ok in checks.items():
        if not ok:
            reasons.append(f"{name} check failed")

    checkpoint_tools = _load_checkpoint_tools(checks)
    registry = CheckpointRegistry(root)

    for role in tuple(required_roles):
        evidence: dict[str, Any] = {
            "ready": False,
            "path": None,
            "sha256": None,
            "status": None,
            "config_vocab_size": None,
            "parameters_finite": None,
        }
        role_evidence[role] = evidence
        hashes[role] = None

        if checkpoint_tools is None:
            reason = f"{role}: cannot validate checkpoint because torch-dependent checkpoint tools are unavailable"
            reasons.append(reason)
            evidence["error"] = reason
            continue

        try:
            resolved = registry.resolve_live(role)
            evidence.update(
                {
                    "path": _display_path(root, resolved.path),
                    "sha256": resolved.sha256,
                    "status": resolved.status,
                    "metrics": resolved.metrics,
                }
            )
            hashes[role] = resolved.sha256

            model, payload = checkpoint_tools["load_checkpoint"](resolved.path)
            vocab_size = payload["config"]["vocab_size"]
            evidence["config_vocab_size"] = vocab_size
            if vocab_size != checkpoint_tools["expected_vocab_size"]:
                raise ValueError(
                    f"wrong vocab size: expected {checkpoint_tools['expected_vocab_size']}, got {vocab_size}"
                )

            parameters_finite = all(
                bool(checkpoint_tools["torch"].isfinite(parameter).all())
                for parameter in model.parameters()
            )
            evidence["parameters_finite"] = parameters_finite
            if not parameters_finite:
                raise ValueError("non-finite parameters detected")

            actual_hash = sha256(resolved.path)
            evidence["actual_sha256"] = actual_hash
            if actual_hash != resolved.sha256:
                raise ValueError(
                    f"hash mismatch: expected {resolved.sha256}, got {actual_hash}"
                )

            evidence["ready"] = True
            roles_ready += 1
        except (FileNotFoundError, LookupError, ValueError, RuntimeError, OSError, KeyError) as exc:
            placeholder_reason = _placeholder_reason(root, role)
            reason = _role_failure_reason(root, role, evidence.get("path"), exc)
            if placeholder_reason:
                reason = f"{reason}; {placeholder_reason}"
            reasons.append(reason)
            evidence["error"] = reason
        except Exception as exc:
            reason = _role_failure_reason(root, role, evidence.get("path"), exc)
            reasons.append(reason)
            evidence["error"] = reason

    result = {
        "verdict": "READY" if not reasons and roles_ready == len(tuple(required_roles)) else "BLOCKED",
        "reasons": reasons,
        "checks": checks,
        "roles_ready": roles_ready,
        "runtime": runtime,
        "hashes": hashes,
        "roles": role_evidence,
    }
    json.dumps(result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run NOVA transformer training preflight checks.")
    parser.add_argument(
        "--project-root",
        default=Path.cwd(),
        type=Path,
        help="Project root containing checkpoints/registry.json.",
    )
    args = parser.parse_args(argv)

    result = run_preflight(args.project_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verdict"] == "READY" else 1


def _load_checkpoint_tools(checks: dict[str, bool]) -> dict[str, Any] | None:
    if not checks["torch"]:
        return None
    try:
        import torch
        from nova_byte_tokenizer import NovaByteTokenizer
        from nova_torch_transformer import load_checkpoint
    except (ImportError, RuntimeError, OSError):
        return None
    return {
        "torch": torch,
        "load_checkpoint": load_checkpoint,
        "expected_vocab_size": NovaByteTokenizer.vocab_size,
    }


def _package_version(package_name: str) -> str | None:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _role_failure_reason(
    root: Path,
    role: str,
    path: object,
    exc: BaseException,
) -> str:
    path_text = str(path) if path else str(_conventional_baseline_path(root, role))
    return f"{role} checkpoint {path_text} invalid: {type(exc).__name__}: {exc}"


def _placeholder_reason(root: Path, role: str) -> str | None:
    path = _conventional_baseline_path(root, role)
    if not path.exists() or not path.is_file():
        return None
    try:
        sample = path.read_bytes()[:4096]
    except OSError as exc:
        return f"could not inspect {path}: {exc}"
    normalized = sample.strip().upper()
    if normalized in {b"PLACEHOLDER", b""} or b"PLACEHOLDER" in normalized:
        return f"{_display_path(root, path)} is a placeholder checkpoint"
    return None


def _conventional_baseline_path(root: Path, role: str) -> Path:
    return root / "checkpoints" / "brain_slots" / role / f"{role}_baseline.pt"


def _display_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
