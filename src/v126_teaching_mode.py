"""v126 — Teaching Mode."""
from __future__ import annotations
from datetime import datetime

def explain_topic(topic, level="beginner"):
    return {"version":"v126_teaching_mode","created_at":datetime.now().isoformat(),
            "topic":topic,"level":level,
            "steps":["Define key concept","Show simple example","Build complexity","Check understanding"],
            "avoids_talking_down":True,"checks_understanding":True,
            "note":"Step-by-step explanation. No false claims."}

def main():
    print("Nova v126 -- Teaching Mode\n")
    r = explain_topic("memory law")
    print(f"Topic: {r['topic']}, Steps: {len(r['steps'])}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
