from __future__ import annotations

from datetime import datetime, timedelta, timezone
import base64
import io
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_perception_fusion import fuse_perception, plan_safe_navigation
from nova_tool_registry import create_default_tool_registry


def test_fusion_separates_observed_inferred_and_unavailable_facts() -> None:
    snapshot = fuse_perception(
        semantic_text="A red chair is near a table.",
        semantic_meta={"used": True, "model": "moondream"},
        ocr_records=[{"text": "EXIT", "confidence": 0.94}],
        scene_report={
            "dominant_colors": ["red"],
            "navigation": {"metric_depth_available": False},
        },
        sensor_snapshot={},
    )

    assert snapshot.semantic_available is True
    assert snapshot.ocr_texts == ("EXIT",)
    assert snapshot.metric_depth_available is False
    assert "metric_distance" in snapshot.unavailable_capabilities
    assert any("chair" in item for item in snapshot.object_observations)
    assert all(item.basis != "verified_detector" for item in snapshot.observations)


def test_safe_trace_never_contains_image_ocr_semantic_or_sensor_content() -> None:
    snapshot = fuse_perception(
        semantic_text="PRIVATE SEMANTIC CONTENT about a chair",
        semantic_meta={"used": True, "model": "moondream"},
        ocr_records=[{"text": "PRIVATE OCR CONTENT", "confidence": 0.99}],
        scene_report={"navigation": {"metric_depth_available": False}},
        sensor_snapshot={"battery": {"level": 0.42}},
    )

    trace = snapshot.safe_trace()
    raw = repr(trace)

    assert trace["image_content_logged"] is False
    assert trace["sensor_values_logged"] is False
    assert "PRIVATE" not in raw
    assert "0.42" not in raw


def test_single_camera_navigation_plan_never_authorizes_movement() -> None:
    snapshot = fuse_perception(
        semantic_text="An open hallway is visible.",
        semantic_meta={"used": True, "model": "moondream"},
        ocr_records=[],
        scene_report={"navigation": {"metric_depth_available": False}},
        sensor_snapshot={},
    )

    plan = plan_safe_navigation(snapshot)

    assert plan.movement_authorized is False
    assert "calibrated depth" in " ".join(plan.required_inputs).lower()
    assert plan.mode == "simulation_only"


def test_only_fresh_calibrated_depth_is_recognized_and_still_does_not_move() -> None:
    now = datetime.now(timezone.utc)
    fresh = fuse_perception(
        semantic_text="A hallway is visible.",
        semantic_meta={"used": True, "model": "moondream"},
        ocr_records=[],
        scene_report={},
        sensor_snapshot={
            "depth": {
                "available": True,
                "calibrated": True,
                "timestamp": now.isoformat(),
            }
        },
        now=now,
    )
    stale = fuse_perception(
        semantic_text="A hallway is visible.",
        semantic_meta={"used": True, "model": "moondream"},
        ocr_records=[],
        scene_report={},
        sensor_snapshot={
            "depth": {
                "available": True,
                "calibrated": True,
                "timestamp": (now - timedelta(seconds=30)).isoformat(),
            }
        },
        now=now,
    )

    assert fresh.metric_depth_available is True
    assert stale.metric_depth_available is False
    assert stale.stale is True
    assert plan_safe_navigation(fresh).movement_authorized is False


def test_registry_exposes_observation_tools_and_disables_physical_movement() -> None:
    registry = create_default_tool_registry()

    vision = registry.get("vision.observe").public_dict()
    robot = registry.get("robot.observe").public_dict()
    movement = registry.get("robot.move").public_dict()

    assert vision["read_write_classification"] == "read"
    assert vision["required_permissions"] == ["vision.observe"]
    assert robot["required_permissions"] == ["robot.observe"]
    assert movement["availability_status"] == "disabled"
    assert movement["required_permissions"] == ["robot.move"]
    assert movement["confirmation_policy"] == "dangerous"


def test_uploaded_picture_attaches_safe_fusion_and_simulation_plan(
    monkeypatch,
) -> None:
    from PIL import Image
    import nova_enhanced_server as server
    import nova_ocr

    image = Image.new("RGB", (32, 32), (180, 20, 20))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")

    monkeypatch.setitem(server.PERMISSIONS, "camera", True)
    monkeypatch.setattr(
        server,
        "_call_moondream_vision",
        lambda *_args, **_kwargs: (
            "A red chair is beside a table. PRIVATE SEMANTIC",
            {"used": True, "model": "moondream", "error": None},
        ),
    )
    monkeypatch.setattr(
        nova_ocr,
        "extract_text",
        lambda *_args, **_kwargs: (
            "EXIT PRIVATE OCR",
            {
                "engine": "tesseract",
                "available": True,
                "used": True,
                "characters": 16,
                "lines": 1,
                "error": None,
            },
        ),
    )

    payload, status = server._vision_response_from_upload(
        {
            "filename": "room.png",
            "mime_type": "image/png",
            "image_base64": encoded,
            "prompt": "Describe everything and plan how a robot could navigate.",
            "sensor_snapshot": {},
        }
    )

    fusion = payload["trace"]["perception_fusion"]
    plan = payload["trace"]["navigation_plan"]
    assert status == 200
    assert fusion["semantic_available"] is True
    assert fusion["ocr_count"] == 1
    assert fusion["metric_depth_available"] is False
    assert fusion["image_content_logged"] is False
    assert plan["mode"] == "simulation_only"
    assert plan["movement_authorized"] is False
    assert "PRIVATE" not in repr(fusion)
    assert "PRIVATE" not in repr(plan)


def test_verified_nova_screen_ocr_overrides_generic_semantic_guess(
    monkeypatch,
) -> None:
    from PIL import Image
    import nova_enhanced_server as server
    import nova_ocr

    image = Image.new("RGB", (32, 32), (10, 10, 40))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    vision_calls = []

    monkeypatch.setitem(server.PERMISSIONS, "camera", True)
    monkeypatch.setattr(
        nova_ocr,
        "extract_text",
        lambda *_args, **_kwargs: (
            "Nova Creature\nChat Home Display\nPic Live Watch Connected Stop All Private",
            {
                "engine": "tesseract",
                "available": True,
                "used": True,
                "characters": 70,
                "lines": 3,
                "error": None,
            },
        ),
    )
    monkeypatch.setattr(
        server,
        "_call_moondream_vision",
        lambda *_args, **_kwargs: vision_calls.append(True)
        or (
            "A generic messaging app is visible.",
            {"used": True, "model": "moondream", "error": None},
        ),
    )

    payload, status = server._vision_response_from_upload(
        {
            "filename": "nova-screen.png",
            "mime_type": "image/png",
            "image_base64": encoded,
            "prompt": "Describe everything and plan safe robot navigation.",
        }
    )

    assert status == 200
    assert vision_calls == []
    assert "This is the Nova Creature app" in payload["response"]
    assert "generic messaging app" not in payload["response"]
    assert (
        payload["trace"]["vision_bypass_reason"]
        == "local_ocr_answered_nova_screen_request"
    )
