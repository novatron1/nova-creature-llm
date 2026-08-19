from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_asset(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_gpu_hub_install_assets_exist() -> None:
    for name in (
        "tools/nova_vast_worker_bootstrap.sh",
        "INSTALL_NOVA_GPU_HUB_WINDOWS.ps1",
        "NOVA_GPU_HUB_INSTALL.bat",
    ):
        assert (ROOT / name).is_file(), name


def test_worker_bootstrap_requires_explicit_engine_model_and_port() -> None:
    content = read_asset("tools/nova_vast_worker_bootstrap.sh")
    assert "set -euo pipefail" in content
    for variable in ("NOVA_WORKER_ENGINE", "NOVA_WORKER_MODEL", "NOVA_WORKER_PORT"):
        assert variable in content
    assert "vllm" in content
    assert "sglang" in content
    assert "Set NOVA_WORKER_ENGINE to vllm or sglang." in content
    assert "ollama)" not in content
    assert "127.0.0.1" in content
    assert "Unsupported NOVA_WORKER_ENGINE" in content


def test_worker_bootstrap_never_advertises_or_launches_unscoped_ollama() -> None:
    content = read_asset("tools/nova_vast_worker_bootstrap.sh")
    assert "exec ollama serve" not in content
    assert "ollama)" not in content


def test_windows_installer_is_checkable_and_does_not_collect_vast_key() -> None:
    content = read_asset("INSTALL_NOVA_GPU_HUB_WINDOWS.ps1")
    assert "[switch]$CheckOnly" in content
    assert "Set-StrictMode -Version Latest" in content
    assert "NOVA_VAST_API_KEY" in content
    assert "setx NOVA_VAST_API_KEY" in content
    assert "Read-Host" not in content
    assert "data" in content
    assert "/healthz" in content


def test_batch_launcher_delegates_without_changing_server_startup() -> None:
    content = read_asset("NOVA_GPU_HUB_INSTALL.bat")
    assert "INSTALL_NOVA_GPU_HUB_WINDOWS.ps1" in content
    assert "powershell" in content.lower()
    assert "nova_enhanced_server.py" not in content


def test_docs_point_to_standalone_gpu_hub_and_health_check() -> None:
    quick_start = read_asset("QUICK_START_LAPTOP.txt")
    readme = read_asset("README_LAPTOP_INSTALL.md")
    assert "GPU Hub" in quick_start
    assert "## GPU Hub (Optional)" in readme
    assert "INSTALL_NOVA_GPU_HUB_WINDOWS.ps1" in readme
    assert "/healthz" in readme
