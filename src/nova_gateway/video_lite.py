"""Local image-to-motion MP4 generation behind Nova's media permissions."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
from threading import Event, RLock, Thread
import time
from typing import Any

from .engines import NovaVideoGenerationEngine
from .errors import (
    InvalidRequestError,
    PermissionDeniedError,
    ProviderUnavailableError,
    UnsupportedFeatureError,
)


VIDEO_LITE_ENGINE_VERSION = "1.0"
VIDEO_LITE_JOB_SCHEMA_VERSION = "1.0"
VIDEO_LITE_MOTIONS = frozenset(
    {"slow_zoom_in", "slow_zoom_out", "pan_left", "pan_right"}
)
_MAX_OUTPUT_BYTES = 1024 * 1024 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validated_int(
    value: Any,
    *,
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidRequestError(f"{name} must be an integer.", param=name)
    if not minimum <= value <= maximum:
        raise InvalidRequestError(
            f"{name} must be between {minimum} and {maximum}.",
            param=name,
        )
    return value


def _resolved_ffmpeg(configured: str | Path | None = None) -> Path | None:
    if configured:
        candidate = Path(os.path.expandvars(str(configured))).expanduser()
        return candidate.resolve() if candidate.is_file() else None
    discovered = shutil.which("ffmpeg")
    if discovered and Path(discovered).is_file():
        return Path(discovered).resolve()
    if os.name != "nt":
        return None

    path_values: list[str] = []
    try:
        import winreg

        registry_locations = (
            (winreg.HKEY_CURRENT_USER, r"Environment"),
            (
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
            ),
        )
        for hive, subkey in registry_locations:
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    path_values.append(str(winreg.QueryValueEx(key, "Path")[0]))
            except OSError:
                continue
    except ImportError:
        pass
    for raw_value in path_values:
        for entry in os.path.expandvars(raw_value).split(os.pathsep):
            if not entry.strip():
                continue
            candidate = Path(entry.strip()) / "ffmpeg.exe"
            if candidate.is_file():
                return candidate.resolve()

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        package_root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        for candidate in sorted(
            package_root.glob("Gyan.FFmpeg*_*/*/bin/ffmpeg.exe"),
            reverse=True,
        ):
            if candidate.is_file():
                return candidate.resolve()
    return None


class NovaVideoLiteEngine(NovaVideoGenerationEngine):
    """Generate a private keyframe, then animate it into a bounded local MP4."""

    engine_id = "nova-video-lite"
    engine_type = "video_generation"
    local_or_remote = "local"
    cost_type = "free"

    def __init__(
        self,
        *,
        enabled: bool = True,
        image_engine: Any | None = None,
        ffmpeg_path: str | Path | None = None,
        output_dir: str | Path = "data/nova_video_lite",
        job_store_path: str | Path | None = "data/nova_video_lite_jobs.json",
        encode_timeout_seconds: int = 180,
    ) -> None:
        self.enabled = bool(enabled)
        self.image_engine = image_engine
        self.ffmpeg_path = _resolved_ffmpeg(ffmpeg_path)
        self.output_dir = Path(output_dir).resolve()
        self.job_store_path = (
            Path(job_store_path).resolve() if job_store_path else None
        )
        self.encode_timeout_seconds = max(30, min(int(encode_timeout_seconds), 1800))
        self._lock = RLock()
        self._store_lock = RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._runtime: dict[str, dict[str, Any]] = {}
        self._job_store_error = ""
        self._load_jobs()

    def _image_health(self) -> dict[str, Any]:
        if self.image_engine is None:
            return {}
        try:
            return dict(self.image_engine.health_check())
        except Exception:
            return {}

    def health_check(self) -> dict[str, Any]:
        image_health = self._image_health()
        image_ready = bool(
            image_health.get("ok")
            and image_health.get("image_workflow_configured")
        )
        ffmpeg_ready = bool(self.ffmpeg_path and self.ffmpeg_path.is_file())
        if not self.enabled:
            status = "disabled"
        elif not ffmpeg_ready:
            status = "ffmpeg_unavailable"
        elif not image_ready:
            status = "image_engine_unavailable"
        else:
            status = "ready"
        return {
            "engine_id": self.engine_id,
            "engine_version": VIDEO_LITE_ENGINE_VERSION,
            "enabled": self.enabled,
            "ok": status == "ready",
            "status": status,
            "local_only": True,
            "cost_type": "free",
            "ffmpeg_available": ffmpeg_ready,
            "image_engine_ready": image_ready,
            "text_to_video": status == "ready",
            "image_to_video": False,
            "video_workflow_configured": status == "ready",
            "job_store_enabled": self.job_store_path is not None,
            "job_store_status": "error" if self._job_store_error else "ready",
            "tracked_jobs": len(self._jobs),
            "motions": sorted(VIDEO_LITE_MOTIONS),
            "maximum_frames": 600,
            "maximum_fps": 60,
            "maximum_duration_seconds": 30,
            "prompt_content_stored": False,
        }

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
            "render_mode": "generated_keyframe_motion",
            "future_worker_compatibility": ["wan2.1-1.3b"],
        }

    def estimate_cost(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "estimated_cost": 0.0,
            "currency": "USD",
            "cost_type": "free",
            "estimated": True,
            "local": True,
        }

    def text_to_video(self, prompt: str, **options: Any) -> dict[str, Any]:
        health = self.health_check()
        if not health.get("ok"):
            raise ProviderUnavailableError(
                "Nova Video Lite requires a ready local image workflow and FFmpeg."
            )
        clean_prompt = " ".join(str(prompt or "").split()).strip()
        if not clean_prompt:
            raise InvalidRequestError(
                "A non-empty generation prompt is required.",
                param="prompt",
            )
        if len(clean_prompt) > 8000:
            raise InvalidRequestError(
                "Generation prompt exceeds 8000 characters.",
                param="prompt",
            )
        negative_prompt = " ".join(
            str(options.get("negative_prompt") or "").split()
        ).strip()
        if len(negative_prompt) > 4000:
            raise InvalidRequestError(
                "negative_prompt exceeds 4000 characters.",
                param="negative_prompt",
            )
        width = _validated_int(
            options.get("width"),
            name="width",
            default=512,
            minimum=256,
            maximum=1024,
        )
        height = _validated_int(
            options.get("height"),
            name="height",
            default=512,
            minimum=256,
            maximum=1024,
        )
        width -= width % 2
        height -= height % 2
        frames = _validated_int(
            options.get("frames"),
            name="frames",
            default=48,
            minimum=8,
            maximum=600,
        )
        fps = _validated_int(
            options.get("fps"),
            name="fps",
            default=12,
            minimum=1,
            maximum=60,
        )
        if frames / fps > 30:
            raise InvalidRequestError(
                "Nova Video Lite clips cannot exceed 30 seconds.",
                param="frames",
            )
        steps = _validated_int(
            options.get("steps"),
            name="steps",
            default=8,
            minimum=1,
            maximum=50,
        )
        seed = _validated_int(
            options.get("seed"),
            name="seed",
            default=secrets.randbelow(2**63 - 1),
            minimum=0,
            maximum=2**63 - 1,
        )
        motion = str(options.get("motion") or "slow_zoom_in").strip().lower()
        if motion not in VIDEO_LITE_MOTIONS:
            raise InvalidRequestError(
                "motion must be slow_zoom_in, slow_zoom_out, pan_left, or pan_right.",
                param="motion",
            )
        owner_id = str(options.get("owner_id") or "local")[:160]
        job_id = "nvl_" + secrets.token_hex(12)
        created_at = _now()
        record = {
            "job_id": job_id,
            "operation": "text_to_video_lite",
            "client_id": owner_id,
            "status": "queued",
            "stage": "queued",
            "created_at": created_at,
            "updated_at": created_at,
            "width": width,
            "height": height,
            "frames": frames,
            "fps": fps,
            "motion": motion,
            "output_filename": "",
            "child_job_id": "",
            "error": None,
        }
        self._remember_job(record)
        cancellation = Event()
        with self._lock:
            self._runtime[job_id] = {"cancel": cancellation, "process": None}
        worker_options = {
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "frames": frames,
            "fps": fps,
            "steps": steps,
            "seed": seed,
            "motion": motion,
        }
        Thread(
            target=self._run_job,
            args=(job_id, clean_prompt, worker_options, cancellation),
            name=f"nova-video-lite-{job_id[-8:]}",
            daemon=True,
        ).start()
        return {
            "object": "nova.media_job",
            "job_id": job_id,
            "engine_id": self.engine_id,
            "operation": "text_to_video_lite",
            "status": "queued",
            "stage": "queued",
            "created_at": created_at,
            "poll_path": f"/nova/v1/jobs/{job_id}",
            "estimated_cost": 0.0,
            "cost_type": "free",
            "local": True,
        }

    def _run_job(
        self,
        job_id: str,
        prompt: str,
        options: dict[str, Any],
        cancellation: Event,
    ) -> None:
        job_dir = self.output_dir / job_id
        keyframe_path = job_dir / "keyframe.image"
        output_path = job_dir / "output.mp4"
        internal_owner = "video-lite:" + job_id
        try:
            job_dir.mkdir(parents=True, exist_ok=True)
            self._update_job(job_id, status="running", stage="generating_keyframe")
            image_job = self.image_engine.generate_image(
                prompt,
                negative_prompt=options["negative_prompt"],
                seed=options["seed"],
                width=options["width"],
                height=options["height"],
                steps=options["steps"],
                owner_id=internal_owner,
            )
            child_job_id = str(image_job.get("job_id") or "")
            if not child_job_id:
                raise ProviderUnavailableError(
                    "The image engine did not return a keyframe job ID."
                )
            self._update_job(job_id, child_job_id=child_job_id)
            while True:
                if cancellation.wait(1.0):
                    try:
                        self.image_engine.cancel_job(
                            child_job_id,
                            owner_id=internal_owner,
                        )
                    except Exception:
                        pass
                    self._mark_cancelled(job_id)
                    return
                child = self.image_engine.job_status(
                    child_job_id,
                    owner_id=internal_owner,
                )
                child_status = str(child.get("status") or "")
                if child_status == "completed":
                    break
                if child_status in {"failed", "cancelled"}:
                    raise ProviderUnavailableError(
                        "The keyframe generation did not complete successfully."
                    )

            opened = self.image_engine.open_job_output(
                child_job_id,
                0,
                owner_id=internal_owner,
            )
            response = opened["response"]
            copied = 0
            try:
                with keyframe_path.open("wb") as target:
                    while True:
                        chunk = response.read(64 * 1024)
                        if not chunk:
                            break
                        copied += len(chunk)
                        if copied > _MAX_OUTPUT_BYTES:
                            raise InvalidRequestError(
                                "Generated keyframe exceeds Nova's output limit."
                            )
                        target.write(chunk)
            finally:
                response.close()
            if not copied:
                raise ProviderUnavailableError(
                    "The image engine returned an empty keyframe."
                )
            if cancellation.is_set():
                self._mark_cancelled(job_id)
                return

            self._update_job(job_id, stage="encoding_motion")
            command = self._ffmpeg_command(keyframe_path, output_path, options)
            creation_flags = (
                subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
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
                if cancellation.wait(0.25):
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
                        "FFmpeg exceeded Nova Video Lite's encoding timeout."
                    )
            if process.returncode != 0 or not output_path.is_file():
                raise ProviderUnavailableError(
                    "FFmpeg could not encode the Nova Video Lite clip."
                )
            if output_path.stat().st_size > _MAX_OUTPUT_BYTES:
                output_path.unlink(missing_ok=True)
                raise InvalidRequestError(
                    "Encoded video exceeds Nova's 1 GB output limit."
                )
            if cancellation.is_set():
                output_path.unlink(missing_ok=True)
                self._mark_cancelled(job_id)
                return
            self._update_job(
                job_id,
                status="completed",
                stage="completed",
                output_filename=output_path.name,
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
            keyframe_path.unlink(missing_ok=True)
            with self._lock:
                self._runtime.pop(job_id, None)

    def _ffmpeg_command(
        self,
        source: Path,
        output: Path,
        options: dict[str, Any],
    ) -> list[str]:
        frames = int(options["frames"])
        fps = int(options["fps"])
        width = int(options["width"])
        height = int(options["height"])
        denominator = max(1, frames - 1)
        motion = str(options["motion"])
        if motion == "slow_zoom_out":
            zoom = f"max(1.0,1.12-on*0.12/{denominator})"
            x = "iw/2-(iw/zoom/2)"
        elif motion == "pan_left":
            zoom = "1.12"
            x = f"(iw-iw/zoom)*(1-on/{denominator})"
        elif motion == "pan_right":
            zoom = "1.12"
            x = f"(iw-iw/zoom)*on/{denominator}"
        else:
            zoom = f"min(1.12,1.0+on*0.12/{denominator})"
            x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
        working_width = width * 2
        working_height = height * 2
        video_filter = (
            f"scale={working_width}:{working_height}:"
            "force_original_aspect_ratio=increase,"
            f"crop={working_width}:{working_height},"
            f"zoompan=z='{zoom}':x='{x}':y='{y}':"
            f"d={frames}:s={width}x{height}:fps={fps},format=yuv420p"
        )
        return [
            str(self.ffmpeg_path),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-loop",
            "1",
            "-i",
            str(source),
            "-vf",
            video_filter,
            "-frames:v",
            str(frames),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ]

    @staticmethod
    def _safe_error(error: Exception) -> str:
        if isinstance(
            error,
            (
                InvalidRequestError,
                ProviderUnavailableError,
                UnsupportedFeatureError,
            ),
        ):
            return str(error)[:500]
        return "Nova Video Lite hit an internal rendering error."

    def image_to_video(self, image: Any, **options: Any) -> dict[str, Any]:
        raise UnsupportedFeatureError(
            "Direct image upload awaits Nova's permission-safe media input adapter."
        )

    def extend_video(self, video: Any, **options: Any) -> dict[str, Any]:
        raise UnsupportedFeatureError("Nova Video Lite cannot extend existing videos.")

    def interpolate_video(self, video: Any, **options: Any) -> dict[str, Any]:
        raise UnsupportedFeatureError(
            "Nova Video Lite does not perform model-based frame interpolation."
        )

    def has_job(self, job_id: str) -> bool:
        with self._lock:
            return str(job_id) in self._jobs

    def _job_record(
        self,
        job_id: str,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            record = dict(self._jobs.get(str(job_id)) or {})
        if not record:
            raise InvalidRequestError(
                "Unknown Nova Video Lite job ID.",
                param="job_id",
            )
        if owner_id is not None and record.get("client_id") != str(owner_id)[:160]:
            raise PermissionDeniedError(
                "This client does not own the requested Nova Video Lite job."
            )
        return record

    def job_status(
        self,
        job_id: str,
        *,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        record = self._job_record(job_id, owner_id)
        outputs: list[dict[str, Any]] = []
        output_path = self.output_dir / str(job_id) / "output.mp4"
        if record.get("status") == "completed":
            if output_path.is_file():
                outputs.append(
                    {
                        "output_index": 0,
                        "media_kind": "video",
                        "filename": f"NovaVideoLite_{job_id}.mp4",
                        "download_path": f"/nova/v1/jobs/{job_id}/outputs/0",
                    }
                )
            else:
                record["status"] = "failed"
                record["stage"] = "failed"
                record["error"] = "The encoded video output is missing."
                self._remember_job(record)
        return {
            "object": "nova.media_job",
            "job_id": str(job_id),
            "engine_id": self.engine_id,
            "operation": record.get("operation"),
            "status": record.get("status"),
            "stage": record.get("stage"),
            "outputs": outputs,
            "error": record.get("error"),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
            "local": True,
            "estimated_cost": 0.0,
            "motion": record.get("motion"),
            "frames": record.get("frames"),
            "fps": record.get("fps"),
        }

    def list_jobs(
        self,
        *,
        owner_id: str,
        limit: int = 25,
    ) -> dict[str, Any]:
        safe_owner = str(owner_id or "")[:160]
        safe_limit = max(1, min(int(limit), 100))
        with self._lock:
            records = [
                dict(record)
                for record in reversed(list(self._jobs.values()))
                if record.get("client_id") == safe_owner
            ][:safe_limit]
        return {
            "object": "list",
            "engine_id": self.engine_id,
            "data": [
                {
                    "object": "nova.media_job",
                    "job_id": record.get("job_id"),
                    "engine_id": self.engine_id,
                    "operation": record.get("operation"),
                    "status": record.get("status"),
                    "stage": record.get("stage"),
                    "created_at": record.get("created_at"),
                    "updated_at": record.get("updated_at"),
                    "poll_path": f"/nova/v1/jobs/{record.get('job_id')}",
                    "local": True,
                    "estimated_cost": 0.0,
                }
                for record in records
            ],
            "privacy": {
                "prompt_content_returned": False,
                "workflow_content_returned": False,
                "other_clients_jobs_returned": False,
            },
        }

    def open_job_output(
        self,
        job_id: str,
        output_index: int,
        *,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        record = self._job_record(job_id, owner_id)
        if output_index != 0:
            raise InvalidRequestError(
                "Nova Video Lite output index is out of range.",
                param="output_index",
            )
        if record.get("status") != "completed":
            raise InvalidRequestError(
                "The Nova Video Lite job has no completed output yet."
            )
        output_path = self.output_dir / str(job_id) / "output.mp4"
        if not output_path.is_file():
            raise InvalidRequestError("The encoded Nova Video Lite output is missing.")
        size = output_path.stat().st_size
        if size > _MAX_OUTPUT_BYTES:
            raise InvalidRequestError(
                "Nova Video Lite output exceeds the 1 GB streaming limit."
            )
        return {
            "response": output_path.open("rb"),
            "content_type": "video/mp4",
            "content_length": size,
            "filename": f"NovaVideoLite_{job_id}.mp4",
            "max_bytes": _MAX_OUTPUT_BYTES,
        }

    def cancel_job(
        self,
        job_id: str,
        *,
        owner_id: str | None = None,
    ) -> bool:
        record = self._job_record(job_id, owner_id)
        if record.get("status") in {"completed", "failed", "cancelled"}:
            return False
        with self._lock:
            runtime = self._runtime.get(str(job_id))
        if runtime is not None:
            runtime["cancel"].set()
            process = runtime.get("process")
            if process is not None and process.poll() is None:
                try:
                    process.terminate()
                except OSError:
                    pass
        child_job_id = str(record.get("child_job_id") or "")
        if child_job_id:
            try:
                self.image_engine.cancel_job(
                    child_job_id,
                    owner_id="video-lite:" + str(job_id),
                )
            except Exception:
                pass
        self._mark_cancelled(str(job_id))
        return True

    def _mark_cancelled(self, job_id: str) -> None:
        self._update_job(
            job_id,
            status="cancelled",
            stage="cancelled",
            error=None,
        )

    def _update_job(self, job_id: str, **changes: Any) -> None:
        record = self._job_record(job_id)
        record.update(changes)
        record["updated_at"] = _now()
        self._remember_job(record)

    def _load_jobs(self) -> None:
        path = self.job_store_path
        if path is None or not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != VIDEO_LITE_JOB_SCHEMA_VERSION:
                return
            records = payload.get("jobs")
            if not isinstance(records, list):
                return
            loaded: dict[str, dict[str, Any]] = {}
            for item in records[-256:]:
                if not isinstance(item, dict):
                    continue
                job_id = str(item.get("job_id") or "")
                if not job_id or not item.get("client_id"):
                    continue
                record = dict(item)
                if record.get("status") in {"queued", "running"}:
                    record["status"] = "failed"
                    record["stage"] = "failed"
                    record["error"] = "Video Lite was interrupted by a Nova restart."
                    record["updated_at"] = _now()
                loaded[job_id] = record
            with self._lock:
                self._jobs = loaded
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            self._job_store_error = "invalid_job_store"

    def _remember_job(self, record: dict[str, Any]) -> None:
        with self._store_lock:
            with self._lock:
                self._jobs[str(record["job_id"])] = dict(record)
                if len(self._jobs) > 256:
                    oldest = next(iter(self._jobs))
                    self._jobs.pop(oldest, None)
                payload = {
                    "schema_version": VIDEO_LITE_JOB_SCHEMA_VERSION,
                    "privacy": {
                        "prompt_content_stored": False,
                        "negative_prompt_content_stored": False,
                        "keyframe_content_stored": False,
                    },
                    "jobs": list(self._jobs.values()),
                }
            path = self.job_store_path
            if path is None:
                return
            temporary = path.with_suffix(path.suffix + ".tmp")
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary.write_text(
                    json.dumps(
                        payload,
                        indent=2,
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                os.replace(temporary, path)
                self._job_store_error = ""
            except OSError:
                self._job_store_error = "job_store_write_failed"
                temporary.unlink(missing_ok=True)
