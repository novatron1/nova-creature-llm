from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import sys
import time

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_gateway.errors import InvalidRequestError, PermissionDeniedError  # noqa: E402
from nova_gateway.video_lite import NovaVideoLiteEngine  # noqa: E402
import nova_gateway.video_lite as video_lite_module  # noqa: E402


class FakeImageEngine:
    def __init__(self, *, completed: bool = True) -> None:
        self.completed = completed
        self.cancelled = []

    def health_check(self):
        return {"ok": True, "image_workflow_configured": True}

    def generate_image(self, prompt, **options):
        self.prompt = prompt
        self.options = options
        return {"job_id": "image-child-1", "status": "queued"}

    def job_status(self, job_id, *, owner_id=None):
        return {
            "job_id": job_id,
            "status": "completed" if self.completed else "running",
        }

    def open_job_output(self, job_id, output_index, *, owner_id=None):
        return {
            "response": BytesIO(b"FAKEPNG"),
            "content_type": "image/png",
            "content_length": 7,
            "filename": "keyframe.png",
            "max_bytes": 1024,
        }

    def cancel_job(self, job_id, *, owner_id=None):
        self.cancelled.append((job_id, owner_id))
        return True


class FakeProcess:
    def __init__(self, command, **_kwargs):
        Path(command[-1]).write_bytes(b"FAKEMP4")
        self.returncode = 0

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = -1

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


def wait_for_terminal(engine: NovaVideoLiteEngine, job_id: str, owner: str):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = engine.job_status(job_id, owner_id=owner)
        if status["status"] in {"completed", "failed", "cancelled"}:
            return status
        time.sleep(0.05)
    raise AssertionError("Video Lite test job did not reach a terminal state.")


def test_video_lite_queues_owned_mp4_without_persisting_prompt(tmp_path, monkeypatch):
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"stub")
    image = FakeImageEngine()
    jobs = tmp_path / "jobs.json"
    engine = NovaVideoLiteEngine(
        image_engine=image,
        ffmpeg_path=ffmpeg,
        output_dir=tmp_path / "outputs",
        job_store_path=jobs,
    )
    monkeypatch.setattr(video_lite_module.subprocess, "Popen", FakeProcess)

    queued = engine.text_to_video(
        "PRIVATE VIDEO PROMPT",
        negative_prompt="PRIVATE NEGATIVE",
        owner_id="phone-one",
        width=512,
        height=512,
        frames=24,
        fps=12,
        steps=8,
        seed=7,
        motion="pan_right",
    )
    completed = wait_for_terminal(engine, queued["job_id"], "phone-one")
    raw_store = jobs.read_text(encoding="utf-8")

    assert queued["engine_id"] == "nova-video-lite"
    assert completed["status"] == "completed"
    assert completed["outputs"][0]["filename"].endswith(".mp4")
    assert completed["motion"] == "pan_right"
    assert "PRIVATE VIDEO PROMPT" not in raw_store
    assert "PRIVATE NEGATIVE" not in raw_store
    assert json.loads(raw_store)["privacy"]["prompt_content_stored"] is False
    assert image.options["owner_id"].startswith("video-lite:")
    with pytest.raises(PermissionDeniedError):
        engine.job_status(queued["job_id"], owner_id="phone-two")

    opened = engine.open_job_output(
        queued["job_id"],
        0,
        owner_id="phone-one",
    )
    assert opened["content_type"] == "video/mp4"
    assert opened["response"].read() == b"FAKEMP4"
    opened["response"].close()


def test_video_lite_validates_bounded_motion_and_duration(tmp_path):
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"stub")
    engine = NovaVideoLiteEngine(
        image_engine=FakeImageEngine(),
        ffmpeg_path=ffmpeg,
        output_dir=tmp_path / "outputs",
        job_store_path=None,
    )

    with pytest.raises(InvalidRequestError, match="motion"):
        engine.text_to_video("test", motion="model_generated_shell_command")
    with pytest.raises(InvalidRequestError, match="30 seconds"):
        engine.text_to_video("test", frames=600, fps=1)
    with pytest.raises(InvalidRequestError, match="width"):
        engine.text_to_video("test", width=2048)


def test_video_lite_cancel_is_owner_scoped(tmp_path):
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"stub")
    image = FakeImageEngine(completed=False)
    engine = NovaVideoLiteEngine(
        image_engine=image,
        ffmpeg_path=ffmpeg,
        output_dir=tmp_path / "outputs",
        job_store_path=None,
    )
    queued = engine.text_to_video("A waiting video", owner_id="phone-one")

    with pytest.raises(PermissionDeniedError):
        engine.cancel_job(queued["job_id"], owner_id="phone-two")
    assert engine.cancel_job(queued["job_id"], owner_id="phone-one") is True
    assert (
        engine.job_status(queued["job_id"], owner_id="phone-one")["status"]
        == "cancelled"
    )


def test_video_lite_health_is_honest_without_encoder_or_image_engine(tmp_path):
    missing_encoder = NovaVideoLiteEngine(
        image_engine=FakeImageEngine(),
        ffmpeg_path=tmp_path / "missing-ffmpeg",
        job_store_path=None,
    )
    no_image = NovaVideoLiteEngine(
        image_engine=None,
        ffmpeg_path=tmp_path / "missing-ffmpeg",
        job_store_path=None,
    )

    assert missing_encoder.health_check()["ok"] is False
    assert no_image.health_check()["ok"] is False
