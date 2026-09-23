from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import time

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_gateway.video_lite import NovaVideoLiteEngine  # noqa: E402
import nova_gateway.video_lite as video_lite_module  # noqa: E402


class _Image:
    def health_check(self):
        return {"ok": True, "image_workflow_configured": True}


class _Process:
    def __init__(self, command, **_kwargs):
        Path(command[-1]).write_bytes(b"VALID_MP4_TEST_OUTPUT")
        self.returncode = 0

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode


def _engine(tmp_path, *, ttl=604800):
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"stub")
    return NovaVideoLiteEngine(
        image_engine=_Image(),
        ffmpeg_path=ffmpeg,
        output_dir=tmp_path / "outputs",
        job_store_path=tmp_path / "jobs.json",
        output_ttl_seconds=ttl,
    )


def test_completed_media_reports_sha256_and_rejects_expired_output(tmp_path, monkeypatch):
    engine = _engine(tmp_path, ttl=604800)
    job_id = "nvl_integrity"
    output = tmp_path / "outputs" / job_id / "output.mp4"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"VALID_MP4_TEST_OUTPUT")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    engine._remember_job(
        {
            "job_id": job_id,
            "client_id": "local",
            "status": "completed",
            "stage": "completed",
            "operation": "text_to_video_lite",
            "created_at": "now",
            "updated_at": "now",
            "output_filename": "output.mp4",
            "output_sha256": digest,
            "output_bytes": output.stat().st_size,
            "output_expires_at": "2999-01-01T00:00:00+00:00",
        }
    )

    status = engine.job_status(job_id, owner_id="local")
    assert status["output_sha256"] == digest
    assert status["output_bytes"] == output.stat().st_size
    assert status["outputs"][0]["sha256"] == digest

    engine._update_job(job_id, output_expires_at="2000-01-01T00:00:00+00:00")
    expired = engine.job_status(job_id, owner_id="local")
    assert expired["status"] == "failed"
    assert "expired" in (expired["error"] or "").lower()


def test_restart_keeps_encoding_checkpoint_resumable(tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    job_id = "nvl_resume"
    checkpoint = tmp_path / "outputs" / job_id / "keyframe.image"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"KEYFRAME")
    record = {
        "job_id": job_id,
        "client_id": "tablet",
        "status": "running",
        "stage": "encoding_motion",
        "operation": "text_to_video_lite",
        "created_at": "now",
        "updated_at": "now",
        "checkpoint_path": str(checkpoint),
        "width": 256,
        "height": 256,
        "frames": 8,
        "fps": 4,
        "motion": "slow_zoom_in",
        "seed": 7,
        "output_filename": "",
        "error": None,
    }
    jobs = tmp_path / "jobs.json"
    jobs.write_text(
        json.dumps({"schema_version": "1.0", "jobs": [record]}),
        encoding="utf-8",
    )
    restarted = _engine(tmp_path)
    assert restarted.job_status(job_id, owner_id="tablet")["status"] == "queued"
    assert restarted.job_status(job_id, owner_id="tablet")["resume_available"] is True

    monkeypatch.setattr(video_lite_module.subprocess, "Popen", _Process)
    resumed = restarted.resume_job(job_id, owner_id="tablet")
    assert resumed["status"] == "queued"
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = restarted.job_status(job_id, owner_id="tablet")
        if status["status"] == "completed":
            break
        time.sleep(0.05)
    assert status["status"] == "completed"
    assert status["output_sha256"]


def test_large_corrupt_payload_is_rejected_by_media_quality_gate(tmp_path):
    engine = _engine(tmp_path)
    job_id = "nvl_corrupt"
    output = tmp_path / "outputs" / job_id / "output.mp4"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"not-an-mp4" * 300)
    engine._remember_job(
        {
            "job_id": job_id,
            "client_id": "local",
            "status": "completed",
            "stage": "completed",
            "operation": "text_to_video_lite",
            "created_at": "now",
            "updated_at": "now",
            "output_filename": "output.mp4",
            "error": None,
        }
    )
    status = engine.job_status(job_id, owner_id="local")
    assert status["status"] == "failed"
    assert "invalid" in (status["error"] or "").lower()
