from __future__ import annotations

"""v068 — Voice / Short Conversation Mode

Lightweight short-conversation mode optimized for quick back-and-forth.
Designed for voice or chat interfaces where responses should be concise.
"""

import json, re, sys
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SHORT_MODE_LOG = ROOT / "data" / "short_conversation" / "short_mode_log.jsonl"


def root() -> Path:
    return ROOT


def ensure_storage() -> None:
    (ROOT / "data" / "short_conversation").mkdir(parents=True, exist_ok=True)


def is_short_mode(message: str) -> bool:
    """Detect if a message is a short/voice-style message."""
    msg = message.strip()
    if len(msg) < 15:
        return True
    # Short questions, commands, follow-ups
    short_patterns = [
        r"^(what|who|where|when|why|how)\s+(is|are|was|does|did|created|made|built|can|will|should|could|would)\s+\w+",
        r"^(ok|okay|go|yes|no|yep|nope|sure|thanks|ty|thx)$",
        r"^(do that|make that|add that|run it|build it|try it)$",
        r"^(next|continue|keep going|what next|and then)$",
        r"^\w{1,10}\??$",
    ]
    return any(re.match(p, msg.strip().lower(), re.IGNORECASE) for p in short_patterns)


def summarize_response(answer: str, route: str | None = None, max_len: int = 100) -> str:
    """Summarize a response for short/voice mode."""
    if not answer or answer == "I do not know.":
        return "I don't know that yet."
    if len(answer) <= max_len:
        return answer
    # Truncate and add ellipsis
    truncated = answer[:max_len].rsplit(" ", 1)[0]
    return truncated + "..."


def process_short_message(
    message: str,
    answer: str | None = None,
    route: str | None = None,
    mode: str = "auto",
) -> dict[str, Any]:
    """Process a message in short-conversation mode."""
    ensure_storage()

    is_short = is_short_mode(message) if mode == "auto" else (mode == "short")
    summary = summarize_response(answer) if answer else None

    event = {
        "version": "v068_short_conversation",
        "created_at": datetime.now().isoformat(),
        "message": message,
        "message_length": len(message.strip()),
        "is_short_mode": is_short,
        "original_answer": answer,
        "short_answer": summary,
        "route": route,
        "mode": mode,
    }

    with SHORT_MODE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    return event


def get_recent_short(limit: int = 10) -> list[dict[str, Any]]:
    if not SHORT_MODE_LOG.exists():
        return []
    lines = [l for l in SHORT_MODE_LOG.read_text().splitlines() if l.strip()]
    events = []
    for line in lines[-limit:]:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return events


def get_summary() -> dict[str, Any]:
    events = get_recent_short(limit=999)
    short_count = sum(1 for e in events if e.get("is_short_mode"))
    return {
        "version": "v068_short_conversation",
        "total_events": len(events),
        "short_mode_events": short_count,
        "storage_path": str(SHORT_MODE_LOG),
    }


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--message", type=str, help="Message to process")
    ap.add_argument("--answer", type=str, default=None, help="Answer to summarize")
    ap.add_argument("--route", type=str, default=None, help="Route label")
    ap.add_argument("--mode", choices=["auto", "short", "full"], default="auto")
    ap.add_argument("--log", action="store_true", help="Show recent log")
    args = ap.parse_args()

    if args.message:
        event = process_short_message(args.message, args.answer, args.route, args.mode)
        print(f"Message:  {event['message']}")
        print(f"Short:    {event['is_short_mode']}")
        print(f"Original: {event['original_answer']}")
        print(f"Summary:  {event['short_answer']}")
        print(f"Route:    {event['route']}")

    if args.log:
        events = get_recent_short()
        print(f"Short conversation log ({len(events)} events):\n")
        for e in events:
            print(f"  {'📢' if e.get('is_short_mode') else '💬'} {e.get('message','')[:50]}")
            print(f"     → {str(e.get('short_answer',''))[:60]}")

    if not args.message and not args.log:
        s = get_summary()
        print("Nova Creature v068 — Voice / Short Conversation Mode\n")
        print(f"Total events:     {s['total_events']}")
        print(f"Short mode hits:  {s['short_mode_events']}")
        print(f"Storage:          {s['storage_path']}")
        print()
        print("Try: --message 'ok go' --answer 'Planner: build the next module'")
        print("     --log")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
