import io
from pathlib import Path
import sys

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_visual_perception import (
    VISUAL_SCENE_SCHEMA_VERSION,
    analyze_scene,
    concise_scene_facts,
    navigation_safety_text,
)


def _scene_bytes() -> bytes:
    image = Image.new("RGB", (120, 80), (80, 205, 225))
    drawing = ImageDraw.Draw(image)
    drawing.rectangle((0, 5, 38, 74), fill=(54, 25, 92))
    drawing.line((5, 8, 34, 70), fill=(245, 245, 250), width=4)
    drawing.line((34, 8, 5, 70), fill=(245, 245, 250), width=4)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_scene_probe_reports_local_pixel_facts_and_left_composition():
    report = analyze_scene(_scene_bytes(), mime_type="image/png")

    assert report["schema_version"] == VISUAL_SCENE_SCHEMA_VERSION
    assert report["engine"] == "pillow_local_scene_probe"
    assert report["dimensions"] == {
        "width": 120,
        "height": 80,
        "orientation": "landscape",
    }
    assert report["local_only"] is True
    assert report["image_persisted"] is False
    assert report["content_logged"] is False
    assert report["appearance"]["dominant_colors"]
    assert report["composition"]["strongest_horizontal_region"]["region"] == "left"
    assert "left side" in concise_scene_facts(report)


def test_single_picture_never_claims_robot_movement_clearance():
    report = analyze_scene(_scene_bytes())
    navigation = report["navigation"]

    assert navigation["semantic_scene_available"] is True
    assert navigation["metric_depth_available"] is False
    assert navigation["obstacle_clearance_verified"] is False
    assert navigation["movement_safe"] is False
    assert any("depth or lidar" in item for item in navigation["required_live_inputs"])
    assert "IMU" in navigation["required_live_inputs"]
    assert "hardware emergency stop" in navigation["required_live_inputs"]
    safety_text = navigation_safety_text(report)
    assert "semantic context only" in safety_text
    assert "not movement clearance" in safety_text


def test_empty_image_is_rejected_honestly():
    try:
        analyze_scene(b"")
    except ValueError as exc:
        assert "required" in str(exc).lower()
    else:
        raise AssertionError("empty image bytes should be rejected")
