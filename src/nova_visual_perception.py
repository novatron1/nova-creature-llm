"""Deterministic, privacy-safe scene facts for Nova picture understanding.

The semantic vision model can name subjects, while this module verifies facts
that should not depend on generative wording: color palette, lighting, regional
composition, and whether one monocular frame is sufficient for robot motion.
Image bytes are analyzed in memory and are never persisted by this module.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import colorsys
import io
from typing import Any

from PIL import Image, ImageFilter, ImageStat


VISUAL_SCENE_SCHEMA_VERSION = "1.0"

@dataclass(frozen=True)
class RegionReading:
    name: str
    brightness: float
    edge_activity: float


def _nearest_color(rgb: tuple[int, int, int]) -> str:
    red, green, blue = rgb
    hue, saturation, value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
    if value < 0.18:
        return "black"
    if saturation < 0.12 and value > 0.82:
        return "white"
    if saturation < 0.16:
        return "gray"
    # Saturated generated-image highlights are better classified by hue than
    # by Euclidean distance to a hand-picked RGB swatch.  This keeps pale cyan
    # light cyan instead of incorrectly calling it white.
    hue_degrees = hue * 360
    if hue_degrees < 15 or hue_degrees >= 345:
        return "red"
    if hue_degrees < 45:
        if value < 0.62:
            return "brown"
        return "orange"
    if hue_degrees < 70:
        return "yellow"
    if hue_degrees < 165:
        return "green"
    if hue_degrees < 195:
        return "cyan"
    if hue_degrees < 255:
        return "blue"
    if hue_degrees < 290:
        return "purple"
    if hue_degrees < 330:
        return "magenta"
    return "pink"


def _palette(image: Image.Image, maximum: int = 5) -> list[dict[str, Any]]:
    sample = image.convert("RGB")
    sample.thumbnail((96, 96))
    quantized = sample.quantize(colors=max(2, min(maximum, 8)))
    colors = sorted(quantized.getcolors() or [], reverse=True)
    palette = quantized.getpalette() or []
    total = max(1, sample.width * sample.height)
    combined: dict[str, dict[str, Any]] = {}
    for count, index in colors:
        offset = int(index) * 3
        if offset + 2 >= len(palette):
            continue
        rgb = tuple(int(value) for value in palette[offset : offset + 3])
        name = _nearest_color(rgb)
        record = combined.setdefault(
            name,
            {"name": name, "hex": "#{:02x}{:02x}{:02x}".format(*rgb), "coverage": 0.0},
        )
        record["coverage"] += count / total
    result = sorted(combined.values(), key=lambda item: item["coverage"], reverse=True)
    for item in result:
        item["coverage"] = round(float(item["coverage"]), 3)
    return result[:maximum]


def _region_readings(gray: Image.Image, edges: Image.Image, *, horizontal: bool) -> list[RegionReading]:
    names = ("left", "center", "right") if horizontal else ("top", "middle", "bottom")
    width, height = gray.size
    readings: list[RegionReading] = []
    for index, name in enumerate(names):
        if horizontal:
            start = round(width * index / 3)
            end = round(width * (index + 1) / 3)
            box = (start, 0, max(start + 1, end), height)
        else:
            start = round(height * index / 3)
            end = round(height * (index + 1) / 3)
            box = (0, start, width, max(start + 1, end))
        readings.append(
            RegionReading(
                name=name,
                brightness=round(float(ImageStat.Stat(gray.crop(box)).mean[0]), 1),
                edge_activity=round(float(ImageStat.Stat(edges.crop(box)).mean[0]), 1),
            )
        )
    return readings


def _focus_region(readings: list[RegionReading], overall_brightness: float) -> dict[str, Any]:
    scored = [
        (
            reading,
            abs(reading.brightness - overall_brightness) + reading.edge_activity * 0.65,
        )
        for reading in readings
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    best, best_score = scored[0]
    second_score = scored[1][1] if len(scored) > 1 else 0.0
    margin = max(0.0, best_score - second_score)
    return {
        "region": best.name,
        "confidence": round(min(0.95, 0.45 + margin / 45.0), 2),
        "score_margin": round(margin, 1),
        "measurement": "regional_luminance_and_edges",
    }


def _lighting_label(brightness: float) -> str:
    if brightness < 55:
        return "dark"
    if brightness < 105:
        return "dim"
    if brightness > 215:
        return "very bright"
    if brightness > 175:
        return "bright"
    return "balanced"


def analyze_scene(image_bytes: bytes, *, mime_type: str = "") -> dict[str, Any]:
    """Return bounded scene facts without retaining image content."""

    if not image_bytes:
        raise ValueError("Image bytes are required for scene analysis.")
    with Image.open(io.BytesIO(image_bytes)) as opened:
        image = opened.convert("RGB")
        width, height = image.size
        sample = image.copy()
    sample.thumbnail((192, 192))
    gray = sample.convert("L")
    stat = ImageStat.Stat(gray)
    brightness = round(float(stat.mean[0]), 1)
    contrast = round(float(stat.stddev[0]), 1)
    edges = gray.filter(ImageFilter.FIND_EDGES)
    horizontal = _region_readings(gray, edges, horizontal=True)
    vertical = _region_readings(gray, edges, horizontal=False)
    horizontal_focus = _focus_region(horizontal, brightness)
    vertical_focus = _focus_region(vertical, brightness)
    orientation = "square" if width == height else ("landscape" if width > height else "portrait")
    palette = _palette(sample)
    return {
        "schema_version": VISUAL_SCENE_SCHEMA_VERSION,
        "engine": "pillow_local_scene_probe",
        "local_only": True,
        "image_persisted": False,
        "content_logged": False,
        "dimensions": {"width": width, "height": height, "orientation": orientation},
        "appearance": {
            "dominant_colors": palette,
            "brightness": brightness,
            "lighting": _lighting_label(brightness),
            "contrast": contrast,
        },
        "composition": {
            "horizontal_regions": [asdict(item) for item in horizontal],
            "vertical_regions": [asdict(item) for item in vertical],
            "strongest_horizontal_region": horizontal_focus,
            "strongest_vertical_region": vertical_focus,
            "claim_scope": "pixel composition only; regions are not object identities",
        },
        "navigation": {
            "semantic_scene_available": True,
            "metric_depth_available": False,
            "traversable_floor_verified": False,
            "obstacle_clearance_verified": False,
            "movement_safe": False,
            "reason": "One monocular image cannot verify distance, clearance, or hidden obstacles.",
            "required_live_inputs": [
                "calibrated depth or lidar",
                "wheel odometry",
                "IMU",
                "bumper or collision sensors",
                "human proximity sensing",
                "battery state",
                "hardware emergency stop",
            ],
        },
    }


def concise_scene_facts(report: dict[str, Any]) -> str:
    """Render deterministic facts suitable for a Nova response."""

    appearance = report.get("appearance") if isinstance(report, dict) else {}
    composition = report.get("composition") if isinstance(report, dict) else {}
    colors = [
        str(item.get("name"))
        for item in (appearance.get("dominant_colors") or [])[:4]
        if isinstance(item, dict) and item.get("name")
    ]
    horizontal = (composition.get("strongest_horizontal_region") or {}).get("region")
    horizontal_confidence = float(
        (composition.get("strongest_horizontal_region") or {}).get("confidence") or 0.0
    )
    dimensions = report.get("dimensions") if isinstance(report, dict) else {}
    color_text = ", ".join(colors) or "not reliably classified"
    focus = ""
    if horizontal and horizontal_confidence >= 0.65:
        focus = f" Strongest pixel contrast/detail is toward the {horizontal} side."
    size = ""
    if dimensions.get("width") and dimensions.get("height"):
        size = f"{dimensions['width']}x{dimensions['height']} {dimensions.get('orientation', '')} image; "
    return (
        f"Verified local scene scan: {size}dominant colors are {color_text}; lighting is "
        f"{appearance.get('lighting', 'unknown')} with contrast {appearance.get('contrast', 'unknown')}."
        f"{focus}"
    )


def navigation_safety_text(report: dict[str, Any]) -> str:
    navigation = report.get("navigation") if isinstance(report, dict) else {}
    return (
        "Navigation safety: this picture is semantic context only, not movement clearance. "
        + str(navigation.get("reason") or "Live ranging and collision sensors are required.")
    )
