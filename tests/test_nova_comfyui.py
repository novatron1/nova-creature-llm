from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_gateway.comfyui import ComfyUIEngine  # noqa: E402
import nova_gateway.comfyui as comfyui_module  # noqa: E402
from nova_gateway.errors import InvalidRequestError, PermissionDeniedError  # noqa: E402


def write_workflow(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "1": {
                    "class_type": "NovaTestNode",
                    "inputs": {
                        "text": "{{NOVA_PROMPT}}",
                        "negative": "{{NOVA_NEGATIVE_PROMPT}}",
                        "seed": "{{NOVA_SEED}}",
                        "width": "{{NOVA_WIDTH}}",
                        "height": "{{NOVA_HEIGHT}}",
                    },
                }
            }
        ),
        encoding="utf-8",
    )


def test_comfyui_rejects_non_loopback_configuration_without_network_access():
    engine = ComfyUIEngine(enabled=True, base_url="https://example.com")
    health = engine.health_check()

    assert health["ok"] is False
    assert health["status"] == "configuration_error"
    assert "local-only" in health["error"]


def test_comfyui_rejects_workflow_that_cannot_receive_nova_prompt(
    tmp_path: Path,
    monkeypatch,
):
    workflow = tmp_path / "broken-api.json"
    workflow.write_text(
        json.dumps({"1": {"class_type": "NovaTestNode", "inputs": {"text": "fixed"}}}),
        encoding="utf-8",
    )
    engine = ComfyUIEngine(enabled=True, image_workflow_path=workflow)
    monkeypatch.setattr(engine, "_request", lambda method, path, payload=None: {})

    with pytest.raises(InvalidRequestError, match="NOVA_PROMPT"):
        engine.generate_image("This prompt must not be silently ignored")


def test_comfyui_queues_typed_workflow_and_persists_only_safe_job_metadata(
    tmp_path: Path,
    monkeypatch,
):
    workflow = tmp_path / "image-api.json"
    jobs = tmp_path / "jobs.json"
    write_workflow(workflow)
    observed = {}
    engine = ComfyUIEngine(
        enabled=True,
        image_workflow_path=workflow,
        job_store_path=jobs,
    )

    def fake_request(method, path, payload=None):
        if path == "/system_stats":
            return {"system": {"ready": True}}
        if path == "/prompt":
            observed.update(method=method, path=path, payload=payload)
            return {"prompt_id": "job-image-1", "number": 1}
        raise AssertionError((method, path, payload))

    monkeypatch.setattr(engine, "_request", fake_request)
    result = engine.generate_image(
        "PRIVATE IMAGE PROMPT",
        negative_prompt="PRIVATE NEGATIVE",
        seed=7,
        width=768,
        height=512,
        owner_id="phone_one",
    )
    node_inputs = observed["payload"]["prompt"]["1"]["inputs"]
    raw_jobs = jobs.read_text(encoding="utf-8")

    assert result["status"] == "queued"
    assert result["job_id"] == "job-image-1"
    assert node_inputs == {
        "text": "PRIVATE IMAGE PROMPT",
        "negative": "PRIVATE NEGATIVE",
        "seed": 7,
        "width": 768,
        "height": 512,
    }
    assert "PRIVATE IMAGE PROMPT" not in raw_jobs
    assert "PRIVATE NEGATIVE" not in raw_jobs
    assert json.loads(raw_jobs)["privacy"]["workflow_content_stored"] is False
    assert json.loads(raw_jobs)["jobs"][0]["client_id"] == "phone_one"
    owned = engine.list_jobs(owner_id="phone_one")
    other = engine.list_jobs(owner_id="phone_two")
    assert owned["data"][0]["job_id"] == "job-image-1"
    assert "client_id" not in owned["data"][0]
    assert other["data"] == []
    assert owned["privacy"]["prompt_content_returned"] is False


def test_comfyui_job_status_outputs_and_owner_isolation(tmp_path: Path, monkeypatch):
    workflow = tmp_path / "image-api.json"
    write_workflow(workflow)
    engine = ComfyUIEngine(enabled=True, image_workflow_path=workflow)
    calls = []

    def fake_request(method, path, payload=None):
        calls.append((method, path, payload))
        if path == "/system_stats":
            return {}
        if path == "/prompt":
            return {"prompt_id": "job-output-1"}
        if path == "/history/job-output-1":
            return {
                "job-output-1": {
                    "status": {"completed": True},
                    "outputs": {
                        "9": {
                            "images": [
                                {
                                    "filename": "nova-output.png",
                                    "subfolder": "",
                                    "type": "output",
                                }
                            ]
                        }
                    },
                }
            }
        raise AssertionError((method, path, payload))

    monkeypatch.setattr(engine, "_request", fake_request)
    engine.generate_image("A safe local image", owner_id="phone_one")
    status = engine.job_status("job-output-1", owner_id="phone_one")

    assert status["status"] == "completed"
    assert status["outputs"][0]["filename"] == "nova-output.png"
    assert status["outputs"][0]["download_path"] == (
        "/nova/v1/jobs/job-output-1/outputs/0"
    )
    assert "view_url" not in status["outputs"][0]
    with pytest.raises(PermissionDeniedError):
        engine.job_status("job-output-1", owner_id="different_phone")

    class FakeOutput:
        headers = {"Content-Type": "image/png", "Content-Length": "7"}

        def read(self, _size=-1):
            return b"PNGDATA"

        def close(self):
            self.closed = True

    fake_output = FakeOutput()
    monkeypatch.setattr(comfyui_module, "urlopen", lambda request, timeout: fake_output)
    opened = engine.open_job_output("job-output-1", 0, owner_id="phone_one")
    assert opened["content_type"] == "image/png"
    assert opened["content_length"] == 7
    assert opened["response"].read() == b"PNGDATA"


def test_comfyui_cancels_only_owned_queued_job(tmp_path: Path, monkeypatch):
    workflow = tmp_path / "video-api.json"
    write_workflow(workflow)
    engine = ComfyUIEngine(enabled=True, video_workflow_path=workflow)
    calls = []

    def fake_request(method, path, payload=None):
        calls.append((method, path, payload))
        if path == "/system_stats":
            return {}
        if path == "/prompt":
            return {"prompt_id": "job-video-1"}
        if path == "/history/job-video-1":
            return {}
        if path == "/queue" and method == "GET":
            return {"queue_running": [], "queue_pending": [[1, "job-video-1"]]}
        if path == "/queue" and method == "POST":
            return {}
        raise AssertionError((method, path, payload))

    monkeypatch.setattr(engine, "_request", fake_request)
    engine.text_to_video("A local animation", owner_id="phone_one")

    with pytest.raises(PermissionDeniedError):
        engine.cancel_job("job-video-1", owner_id="different_phone")
    assert engine.cancel_job("job-video-1", owner_id="phone_one") is True
    assert ("POST", "/queue", {"delete": ["job-video-1"]}) in calls
