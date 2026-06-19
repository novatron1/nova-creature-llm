"""v771_auto_greeting_engine — Natural People Memory Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re
ROOT = Path(__file__).resolve().parents[1]

def auto_greeting_engine(person_status=None, person_name=None):
    """Generate natural greetings for known, new, and uncertain people."""
    if person_status == "known_person" and person_name:
        greeting = f"Hello again, {person_name}! Good to see you."
    elif person_status == "new_introduction" and person_name:
        greeting = f"Nice to meet you, {person_name}! I am Nova."
    elif person_status == "possible_match" and person_name:
        greeting = f"Is this still {person_name}? I want to make sure I remember correctly."
    elif person_status == "low_confidence_match":
        greeting = "You look familiar but I am not sure. Remind me your name?"
    else:
        greeting = "Hello! I am Nova. What is your name?"
    return {"version": "v771_auto_greeting_engine", "created_at": datetime.now().isoformat(),
            "greeting": greeting, "person_status": person_status or "unknown", "status": "ok"}


def main():
    import sys
    print(f"Nova v771_auto_greeting_engine")
    r = auto_greeting_engine()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
