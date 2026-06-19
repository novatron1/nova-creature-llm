"""v078 — Voice / Short Conversation Mode."""
from __future__ import annotations
from datetime import datetime
from typing import Any

MODES = ["voice_short", "voice_project", "voice_coding", "voice_robot_sim", "voice_deep"]
SHORT_COMMANDS = {
    "do that": "voice_project",
    "what next": "voice_project",
    "run it": "voice_coding",
    "go": "voice_project",
    "stop": "voice_robot_sim",
    "continue": "voice_project",
    "tell me short": "voice_short",
    "is robot movement active": "voice_robot_sim",
}


def classify_mode(text: str) -> str:
    t = text.lower().strip()
    if t in SHORT_COMMANDS:
        return SHORT_COMMANDS[t]
    if any(w in t for w in ["code", "write", "script", "function"]):
        return "voice_coding"
    if any(w in t for w in ["robot", "move", "simulat"]):
        return "voice_robot_sim"
    if any(w in t for w in ["explain", "describe", "detail", "deep"]):
        return "voice_deep"
    if any(w in t for w in ["project", "build", "upgrade", "version"]):
        return "voice_project"
    return "voice_short"


def clean_text(text: str) -> str:
    return " ".join(text.strip().split())


def process_voice(text: str, context: dict | None = None) -> dict:
    cleaned = clean_text(text)
    mode = classify_mode(cleaned)
    short_answer = mode in ("voice_short", "voice_project", "voice_robot_sim")
    return {
        "version": "v078_voice_mode",
        "original": text,
        "cleaned": cleaned,
        "mode": mode,
        "short_answer": short_answer,
        "is_short_command": cleaned.lower() in SHORT_COMMANDS,
        "context_preserved": bool(context),
        "created_at": datetime.now().isoformat(),
        "real_hardware_enabled": False,
    }


def main() -> int:
    print("Nova v078 -- Voice Mode\n")
    msgs = ["Do that", "What next", "Run it", "Is robot movement active", "Tell me short"]
    for msg in msgs:
        result = process_voice(msg)
        print(f"  {msg:30s} -> mode={result['mode']}, short={result['short_answer']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
