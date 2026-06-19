"""v062 — Growth Engine

Captures events from all growth streams and routes them through the pipeline.
"""

from __future__ import annotations

import json, re
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

ROLE_KEYWORDS = {
    "left_hemisphere": ["math", "plus", "minus", "times", "code", "logic", "test", "calculate"],
    "right_hemisphere": ["imagine", "creative", "pattern", "visual", "architecture", "map", "idea"],
    "memory_transformer": ["who", "name", "created", "made", "built", "remember", "memory", "fact"],
    "planner_transformer": ["next", "plan", "build", "step", "upgrade", "install", "fix"],
    "critic_conscience_transformer": ["favorite", "unknown", "guess", "safe", "wrong", "true"],
    "dream_simulation_transformer": ["dream", "practice", "scenario", "variant", "replay", "simulate"],
    "speech_output_transformer": ["say", "explain", "answer", "respond", "word", "clean"],
}


def root() -> Path:
    return ROOT


def normalize(text: str) -> str:
    s = str(text or "").lower().strip()
    s = re.sub(r"[^a-z0-9+\-*x ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def classify_role(source_text: str) -> str:
    text = normalize(source_text)
    for role, keywords in ROLE_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return role
    return "memory_transformer"


def capture_growth_event(
    source_text: str,
    stream_name: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Capture a growth event, classify it, and store it in the appropriate stream."""
    from v062_growth_streams import get_stream

    # Auto-detect stream from text if not provided
    if stream_name is None:
        ctx = context or {}
        q = normalize(source_text)
        if "remember" in q or "save" in q:
            stream_name = "conversation_corrections"
        elif "the correct answer" in q or "answer is" in q:
            stream_name = "dictionary_facts"
        elif "error" in q or "fail" in q or "mistake" in q:
            stream_name = "error_reports"
        elif "dream" in q or "replay" in q:
            stream_name = "dream_replay"
        elif "benchmark" in q or "test" in q:
            stream_name = "benchmark_results"
        elif "script" in q:
            stream_name = "script_test_results"
        elif "robot" in q or "simulat" in q or "movement" in q:
            stream_name = "robot_simulation_results"
        elif "project" in q or "build" in q or "upgrade" in q:
            stream_name = "project_reports"
        else:
            stream_name = "conversation_corrections"

    stream_info = get_stream(stream_name)
    if stream_info is None:
        return {"error": f"Unknown growth stream: {stream_name}"}

    role_target = classify_role(source_text)
    confidence = 0.8 if stream_info["risk_level"] == "low" else 0.6
    requires_approval = stream_info["requires_approval"]
    trainable = stream_info["trainable"] and not requires_approval

    event = {
        "version": "v062_growth_engine",
        "event_id": f"ge_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
        "created_at": datetime.now().isoformat(),
        "stream_name": stream_name,
        "source_text": source_text,
        "extracted_lesson": source_text[:200],
        "role_target": role_target,
        "confidence": confidence,
        "requires_approval": requires_approval,
        "trainable": trainable,
        "risk_level": stream_info["risk_level"],
        "reason": stream_info["description"],
        "context": context or {},
    }

    # Store in growth stream file
    stream_path = root() / "data" / "growth_streams" / f"{stream_name}.jsonl"
    stream_path.parent.mkdir(parents=True, exist_ok=True)
    with stream_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    return event


def list_stream_events(stream_name: str, limit: int = 20) -> list[dict[str, Any]]:
    path = root() / "data" / "growth_streams" / f"{stream_name}.jsonl"
    if not path.exists():
        return []
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    events = []
    for line in lines[-limit:]:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return events


def get_all_counts() -> dict[str, int]:
    counts = {}
    streams_dir = root() / "data" / "growth_streams"
    if not streams_dir.exists():
        return counts
    for f in sorted(streams_dir.glob("*.jsonl")):
        name = f.stem
        count = sum(1 for l in f.read_text().splitlines() if l.strip())
        counts[name] = count
    return counts
