"""CPU-only AnimateDiff video engine for Nova Dream Studio."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import time
from typing import Any

from .errors import InvalidRequestError, ProviderUnavailableError
from .video_lite import NovaVideoLiteEngine, _MAX_OUTPUT_BYTES


def build_animatediff_worker_command(
    *,
    python_path: str | Path,
    worker_script: str | Path,
    model_path: str | Path,
    motion_adapter_path: str | Path,
    output_path: str | Path,
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    frames: int,
    fps: int,
    steps: int,
    seed: int,
    device: str = "cpu",
) -> list[str]:
    return [
        str(python_path),
        str(worker_script),
        "--model-path",
        str(model_path),
        "--motion-adapter-path",
        str(motion_adapter_path),
        "--output",
        str(output_path),
        "--prompt",
        prompt,
        "--negative-prompt",
        negative_prompt,
        "--width",
        str(width),
        "--height",
        str(height),
        "--frames",
        str(frames),
        "--fps",
        str(fps),
        "--steps",
        str(steps),
        "--seed",
        str(seed),
        "--device",
        str(device),
        "--local-files-only",
    ]


class NovaAnimateDiffCpuEngine(NovaVideoLiteEngine):
    """Generate real temporal motion with AnimateDiff on the local CPU."""

    engine_id = "nova-animatediff-cpu"
    engine_type = "video_generation"
    local_or_remote = "local"
    cost_type = "free"
    job_prefix = "nad_"

    def __init__(
        self,
        *,
        enabled: bool = True,
        device: str = "cpu",
        engine_id: str | None = None,
        job_prefix: str | None = None,
        display_name: str | None = None,
        python_path: str | Path | None = None,
        worker_script: str | Path | None = None,
        model_path: str | Path | None = None,
        motion_adapter_path: str | Path | None = None,
        output_dir: str | Path = "data/nova_animatediff_cpu",
        job_store_path: str | Path | None = "data/nova_animatediff_cpu_jobs.json",
        encode_timeout_seconds: int = 3600,
        output_ttl_seconds: int = 7 * 24 * 60 * 60,
    ) -> None:
        self.device = str(device or "cpu").strip().lower()
        self.engine_id = str(engine_id or self.engine_id)
        self.job_prefix = str(job_prefix or self.job_prefix)
        self.display_name = str(display_name or "AnimateDiff CPU")
        super().__init__(
            enabled=enabled,
            image_engine=None,
            ffmpeg_path=None,
            output_dir=output_dir,
            job_store_path=job_store_path,
            encode_timeout_seconds=180,
            output_ttl_seconds=output_ttl_seconds,
        )
        self.python_path = Path(python_path).expanduser().resolve() if python_path else None
        self.worker_script = Path(worker_script).expanduser().resolve() if worker_script else None
        self.model_path = Path(model_path).expanduser().resolve() if model_path else None
        self.motion_adapter_path = (
            Path(motion_adapter_path).expanduser().resolve()
            if motion_adapter_path
            else None
        )
        self.encode_timeout_seconds = max(60, min(int(encode_timeout_seconds), 7200))

    def health_check(self) -> dict[str, Any]:
        if not self.enabled:
            status = "disabled"
        elif self.device == "cuda" and not self._cuda_available():
            status = "gpu_unavailable"
        elif not self.python_path or not self.python_path.is_file():
            status = "worker_unavailable"
        elif not self.worker_script or not self.worker_script.is_file():
            status = "worker_unavailable"
        elif not self.model_path or not (self.model_path / "model_index.json").is_file():
            status = "model_unavailable"
        elif not self.motion_adapter_path or not (
            self.motion_adapter_path / "config.json"
        ).is_file():
            status = "model_unavailable"
        elif not (
            (self.motion_adapter_path / "diffusion_pytorch_model.fp16.safetensors").is_file()
            or (self.motion_adapter_path / "diffusion_pytorch_model.safetensors").is_file()
        ):
            status = "model_unavailable"
        else:
            status = "ready"
        return {
            "engine_id": self.engine_id,
            "engine_version": "1.0",
            "enabled": self.enabled,
            "ok": status == "ready",
            "status": status,
            "local_only": True,
            "cost_type": "free",
            "ffmpeg_available": True,
            "image_engine_ready": True,
            "text_to_video": status == "ready",
            "image_to_video": False,
            "video_workflow_configured": status == "ready",
            "render_mode": "animatediff_cpu",
            "motion_model": "animatediff-motion-adapter-v1-5-2",
            "job_store_enabled": self.job_store_path is not None,
            "job_store_status": "error" if self._job_store_error else "ready",
            "tracked_jobs": len(self._jobs),
            "motions": [],
            "maximum_frames": 32,
            "maximum_fps": 12,
            "maximum_duration_seconds": 8,
            "prompt_content_stored": False,
        }

    def _cuda_available(self) -> bool:
        """Probe CUDA in the worker interpreter, not the API server Python."""
        if not self.python_path or not self.python_path.is_file():
            return False
        try:
            result = subprocess.run(
                [str(self.python_path), "-c", "import torch; print(torch.cuda.is_available())"],
                capture_output=True,
                text=True,
                # CUDA initialization in the F: venv can take several
                # seconds on a cold start while DLLs are loaded.
                timeout=60,
                check=False,
            )
            return result.returncode == 0 and result.stdout.strip().splitlines()[-1].lower() == "true"
        except (OSError, subprocess.SubprocessError, IndexError):
            return False

    def capabilities(self) -> dict[str, Any]:
        health = self.health_check()
        return {
            "engine_id": self.engine_id,
            "available": bool(health.get("ok")),
            "text_to_video": bool(health.get("ok")),
            "image_to_video": False,
            "video_extension": False,
            "video_interpolation": False,
            "async_jobs": True,
            "job_cancellation": True,
            "local_only": True,
            "cost_type": "free",
            "render_mode": "animatediff_cpu",
            "motion_model": "animatediff-motion-adapter-v1-5-2",
        }

    def _output_filename(self, job_id: str) -> str:
        label = "".join(ch for ch in self.display_name if ch.isalnum())
        return f"{label}_{job_id}.mp4"

    def text_to_video(self, prompt: str, **options: Any) -> dict[str, Any]:
        result = super().text_to_video(prompt, **options)
        job_id = str(result.get("job_id") or "")
        if job_id:
            self._update_job(job_id, operation=f"text_to_video_{self.job_prefix.rstrip('_')}")
        result["engine_id"] = self.engine_id
        result["operation"] = f"text_to_video_{self.job_prefix.rstrip('_')}"
        return result

    def _run_job(
        self,
        job_id: str,
        prompt: str,
        options: dict[str, Any],
        cancellation,
        resume_from_checkpoint: bool = False,
    ) -> None:
        if resume_from_checkpoint:
            self._update_job(
                job_id,
                status="failed",
                stage="failed",
                error=f"{self.display_name} cannot resume an interrupted model render.",
            )
            return
        job_dir = self.output_dir / job_id
        output_path = job_dir / "output.mp4"
        try:
            job_dir.mkdir(parents=True, exist_ok=True)
            self._update_job(
                job_id,
                status="running",
                stage=f"generating_{self.job_prefix.rstrip('_')}",
            )
            command = build_animatediff_worker_command(
                python_path=self.python_path,
                worker_script=self.worker_script,
                model_path=self.model_path,
                motion_adapter_path=self.motion_adapter_path,
                output_path=output_path,
                prompt=prompt,
                negative_prompt=str(options.get("negative_prompt") or ""),
                width=int(options["width"]),
                height=int(options["height"]),
                frames=int(options["frames"]),
                fps=int(options["fps"]),
                steps=int(options["steps"]),
                seed=int(options["seed"]),
                device=self.device,
            )
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                creationflags=creation_flags,
            )
            with self._lock:
                runtime = self._runtime.get(job_id)
                if runtime is not None:
                    runtime["process"] = process
            deadline = time.monotonic() + self.encode_timeout_seconds
            while process.poll() is None:
                if cancellation.wait(0.5):
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    self._mark_cancelled(job_id)
                    return
                if time.monotonic() > deadline:
                    process.kill()
                    raise ProviderUnavailableError(
                        f"{self.display_name} exceeded Nova's video generation timeout."
                    )
            if process.returncode != 0 or not output_path.is_file():
                raise ProviderUnavailableError(
                    f"{self.display_name} could not encode a video output."
                )
            if output_path.stat().st_size > _MAX_OUTPUT_BYTES:
                output_path.unlink(missing_ok=True)
                raise ProviderUnavailableError(f"{self.display_name} output exceeds Nova's 1 GB limit.")
            integrity = self._output_integrity(output_path)
            self._update_job(
                job_id,
                status="completed",
                stage="completed",
                output_filename=output_path.name,
                output_sha256=integrity["sha256"],
                output_bytes=integrity["bytes"],
                output_expires_at=integrity["expires_at"],
                error=None,
            )
        except Exception as exc:
            current = self._job_record(job_id)
            if current.get("status") != "cancelled":
                self._update_job(
                    job_id,
                    status="failed",
                    stage="failed",
                    error=self._safe_error(exc),
                )
        finally:
            with self._lock:
                self._runtime.pop(job_id, None)

    @staticmethod
    def _safe_error(error: Exception) -> str:
        if isinstance(error, (InvalidRequestError, ProviderUnavailableError)):
            return str(error)[:500]
        return "AnimateDiff render hit an internal rendering error."

    def resume_job(self, job_id: str, *, owner_id: str | None = None) -> dict[str, Any]:
        raise InvalidRequestError(
            f"{self.display_name} cannot resume an interrupted model render; start a new job.",
            param="job_id",
        )


class NovaAnimateDiffGpuEngine(NovaAnimateDiffCpuEngine):
    """Generate real temporal motion with AnimateDiff on the local GPU."""

    engine_id = "nova-animatediff-gpu"
    job_prefix = "nag_"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            device="cuda",
            engine_id=self.engine_id,
            job_prefix=self.job_prefix,
            display_name="AnimateDiff GPU",
            **kwargs,
        )
