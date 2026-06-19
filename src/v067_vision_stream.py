from __future__ import annotations

"""v067 — Vision / Screenshot Learning Stream

Architectural skeleton for visual input processing.

This module defines the interface for:
1. Ingesting screenshots or images
2. Extracting text/description from visual input
3. Creating training lessons from visual observations
4. Storing vision-derived facts in smart memory

Current environment: cloud terminal (no GPU/compute vision).
When a vision model or API is connected, this module routes
visual input into the existing learning pipeline.

Usage (future):
    from v067_vision_stream import process_visual_input
    process_visual_input("path/to/screenshot.png")
"""

import json, hashlib
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VISION_LOG = ROOT / "data" / "vision_stream" / "vision_log.jsonl"


def root() -> Path:
    return ROOT


def ensure_storage() -> None:
    (ROOT / "data" / "vision_stream").mkdir(parents=True, exist_ok=True)


def log_vision_event(event: dict[str, Any]) -> None:
    ensure_storage()
    with VISION_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def process_visual_input(
    image_path: str | Path,
    description: str | None = None,
    source: str = "manual",
) -> dict[str, Any]:
    """Process a visual input (screenshot/image).

    Args:
        image_path: Path to the image file (local or future URL).
        description: Optional human-provided description of the image.
        source: Source label ('manual', 'screenshot', 'upload', etc.).

    Returns:
        dict with event_id, status, text_extracted (placeholder), and storage info.
    """
    path = Path(image_path)
    event = {
        "version": "v067_vision_stream",
        "event_id": f"vis_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
        "created_at": datetime.now().isoformat(),
        "image_path": str(path),
        "image_exists": path.exists(),
        "image_size_bytes": path.stat().st_size if path.exists() else 0,
        "image_hash": _file_hash(path) if path.exists() else None,
        "description": description or "(no description provided)",
        "text_extracted": "(vision model not connected — placeholder)",
        "source": source,
        "status": "logged_no_vision_model",
        "note": "v067 defines the interface. Connect a vision model or API to extract actual text.",
    }
    log_vision_event(event)
    return event


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def get_vision_log(limit: int = 10) -> list[dict[str, Any]]:
    if not VISION_LOG.exists():
        return []
    lines = [l for l in VISION_LOG.read_text().splitlines() if l.strip()]
    events = []
    for line in lines[-limit:]:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return events


def get_stream_summary() -> dict[str, Any]:
    events = get_vision_log(limit=999)
    return {
        "version": "v067_vision_stream",
        "total_events": len(events),
        "vision_model_connected": False,
        "storage_path": str(VISION_LOG),
        "status": "interface_defined_awaiting_model",
    }


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="v067 Vision/Screenshot Stream")
    ap.add_argument("--image", type=str, help="Path to image file")
    ap.add_argument("--describe", type=str, default=None, help="Optional description")
    ap.add_argument("--log", action="store_true", help="Show recent vision log")
    args = ap.parse_args()

    if args.image:
        result = process_visual_input(args.image, description=args.describe)
        print(f"Vision event logged: {result['event_id']}")
        print(f"  Status: {result['status']}")
        print(f"  Note: {result['note']}")

    if args.log:
        events = get_vision_log()
        print(f"Vision log ({len(events)} events):\n")
        for e in events:
            print(f"  [{e.get('event_id','')}] {e.get('image_path','')}")
            print(f"      {e.get('description','')[:60]}")
            print(f"      {e.get('status')}")

    if not args.image and not args.log:
        summary = get_stream_summary()
        print("Nova Creature v067 — Vision/Screenshot Learning Stream\n")
        print(f"Events logged: {summary['total_events']}")
        print(f"Vision model:  {'CONNECTED' if summary['vision_model_connected'] else 'NOT CONNECTED'}")
        print(f"Storage:       {summary['storage_path']}")
        print(f"Status:        {summary['status']}")
        print()
        print("To log a vision event: --image <path> [--describe <text>]")
        print("To view log:           --log")
        print("Note: This is the interface skeleton. Connect a vision model")
        print("      (CLIP, GPT-4V, etc.) to enable actual text extraction.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
