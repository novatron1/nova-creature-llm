from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_gateway.animatediff_cpu import (  # noqa: E402
    NovaAnimateDiffCpuEngine,
    build_animatediff_worker_command,
)
from nova_gateway.config import GatewayConfig  # noqa: E402
from scripts import nova_animatediff_cpu_worker as animatediff_worker  # noqa: E402


class _PipelinePlacementProbe:
    def __init__(self):
        self.offload_enabled = False
        self.moved_to = None

    def enable_model_cpu_offload(self):
        self.offload_enabled = True

    def to(self, device):
        self.moved_to = device


def test_animatediff_cpu_health_requires_local_worker_and_models(tmp_path):
    python_path = tmp_path / "python.exe"
    worker_script = tmp_path / "worker.py"
    python_path.write_bytes(b"stub")
    worker_script.write_bytes(b"stub")
    engine = NovaAnimateDiffCpuEngine(
        enabled=True,
        python_path=python_path,
        worker_script=worker_script,
        model_path=tmp_path / "sd15",
        motion_adapter_path=tmp_path / "motion",
        output_dir=tmp_path / "outputs",
        job_store_path=None,
    )

    health = engine.health_check()

    assert health["engine_id"] == "nova-animatediff-cpu"
    assert health["local_only"] is True
    assert health["text_to_video"] is False
    assert health["status"] == "model_unavailable"


def test_animatediff_cpu_worker_command_is_local_and_cpu_bound(tmp_path):
    command = build_animatediff_worker_command(
        python_path=tmp_path / "python.exe",
        worker_script=tmp_path / "worker.py",
        model_path=tmp_path / "sd15",
        motion_adapter_path=tmp_path / "motion",
        output_path=tmp_path / "output.mp4",
        prompt="Nova moves",
        negative_prompt="blurry",
        width=256,
        height=256,
        frames=16,
        fps=8,
        steps=2,
        seed=42,
    )

    assert command[0] == str(tmp_path / "python.exe")
    assert command[1] == str(tmp_path / "worker.py")
    assert "--device" in command and command[command.index("--device") + 1] == "cpu"
    assert "--local-files-only" in command
    assert command[command.index("--frames") + 1] == "16"
    assert command[command.index("--output") + 1] == str(tmp_path / "output.mp4")


def test_gateway_config_reads_animatediff_cpu_worker_settings(tmp_path):
    config = GatewayConfig.from_env(
        {
            "NOVA_ANIMATEDIFF_CPU_ENABLED": "true",
            "NOVA_ANIMATEDIFF_CPU_PYTHON": "worker-python.exe",
            "NOVA_ANIMATEDIFF_CPU_WORKER": "worker.py",
            "NOVA_ANIMATEDIFF_CPU_MODEL": "models/sd15",
            "NOVA_ANIMATEDIFF_CPU_MOTION_ADAPTER": "models/motion",
            "NOVA_ANIMATEDIFF_CPU_TIMEOUT": "4200",
        },
        root=tmp_path,
    )

    assert config.animatediff_cpu_enabled is True
    assert config.animatediff_cpu_python_path == (tmp_path / "worker-python.exe").resolve()
    assert config.animatediff_cpu_worker_path == (tmp_path / "worker.py").resolve()
    assert config.animatediff_cpu_model_path == (tmp_path / "models" / "sd15").resolve()
    assert config.animatediff_cpu_motion_adapter_path == (
        tmp_path / "models" / "motion"
    ).resolve()
    assert config.animatediff_cpu_timeout_seconds == 4200


def test_dream_studio_selects_animatediff_cpu_for_video_when_available():
    script = (ROOT / "assets" / "nova_dream_studio.js").read_text(encoding="utf-8")
    assert "nova-animatediff-cpu" in script
    assert "AnimateDiff CPU ready" in script


def test_cpu_worker_normalizes_weights_and_avoids_fp16_cpu_execution():
    worker = (ROOT / "scripts" / "nova_animatediff_cpu_worker.py").read_text(encoding="utf-8")
    assert "torch.float32 if args.device == \"cpu\"" in worker
    assert "diffusion_pytorch_model.fp16.safetensors" in worker
    assert "diffusion_pytorch_model.safetensors" in worker
    assert "enable_vae_slicing" in worker


def test_gpu_worker_offloads_pipeline_components_to_fit_available_vram():
    pipe = _PipelinePlacementProbe()

    assert hasattr(animatediff_worker, "configure_pipeline_device")
    placement = animatediff_worker.configure_pipeline_device(pipe, "cuda")

    assert placement == "model_cpu_offload"
    assert pipe.offload_enabled is True
    assert pipe.moved_to is None


def test_cpu_worker_keeps_pipeline_on_cpu():
    pipe = _PipelinePlacementProbe()

    assert hasattr(animatediff_worker, "configure_pipeline_device")
    placement = animatediff_worker.configure_pipeline_device(pipe, "cpu")

    assert placement == "direct_cpu"
    assert pipe.offload_enabled is False
    assert pipe.moved_to == "cpu"
