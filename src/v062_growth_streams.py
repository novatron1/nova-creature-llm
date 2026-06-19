"""v062 — Growth Streams Registry

Defines all growth streams Nova can learn from.
"""

from __future__ import annotations

from typing import Any

GROWTH_STREAMS = {
    "conversation_corrections": {
        "description": "User corrections during conversation",
        "requires_approval": False,
        "trainable": True,
        "risk_level": "low",
    },
    "dictionary_facts": {
        "description": "Approved dictionary Q&A entries",
        "requires_approval": False,
        "trainable": True,
        "risk_level": "low",
    },
    "project_reports": {
        "description": "Project build status and reports",
        "requires_approval": False,
        "trainable": False,
        "risk_level": "low",
    },
    "error_reports": {
        "description": "Mistakes and error patterns",
        "requires_approval": True,
        "trainable": True,
        "risk_level": "medium",
    },
    "dream_replay": {
        "description": "Dream-generated practice lessons",
        "requires_approval": True,
        "trainable": True,
        "risk_level": "medium",
    },
    "user_rules": {
        "description": "User-defined rules and preferences",
        "requires_approval": True,
        "trainable": True,
        "risk_level": "medium",
    },
    "codex_reports": {
        "description": "Codex CLI session outcomes",
        "requires_approval": False,
        "trainable": False,
        "risk_level": "low",
    },
    "benchmark_results": {
        "description": "Benchmark test outcomes",
        "requires_approval": False,
        "trainable": False,
        "risk_level": "low",
    },
    "screenshot_reports": {
        "description": "Visual input observations",
        "requires_approval": True,
        "trainable": True,
        "risk_level": "medium",
    },
    "voice_transcripts": {
        "description": "Voice/speech input transcripts",
        "requires_approval": True,
        "trainable": True,
        "risk_level": "medium",
    },
    "script_test_results": {
        "description": "Self-scripting test outcomes",
        "requires_approval": False,
        "trainable": False,
        "risk_level": "low",
    },
    "robot_simulation_results": {
        "description": "Robot simulation test results",
        "requires_approval": True,
        "trainable": True,
        "risk_level": "high",
    },
}


def get_stream(name: str) -> dict[str, Any] | None:
    return GROWTH_STREAMS.get(name)


def list_streams() -> list[str]:
    return list(GROWTH_STREAMS.keys())


def get_trainable_streams() -> list[str]:
    return [k for k, v in GROWTH_STREAMS.items() if v["trainable"]]


def get_streams_requiring_approval() -> list[str]:
    return [k for k, v in GROWTH_STREAMS.items() if v["requires_approval"]]
