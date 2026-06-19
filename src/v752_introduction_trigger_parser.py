"""v752_introduction_trigger_parser — Natural People Memory Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re
ROOT = Path(__file__).resolve().parents[1]

def introduction_trigger_parser(text=""):
    """Detect natural introduction phrases and extract name/relationship."""
    patterns = [
        (r"(?i:my name is) ([A-Z][a-z]+)", "self_introduction", "full_name"),
        (r"(?i:i'm) ([A-Z][a-z]*)", "self_introduction", "first_name"),
        (r"(?i:i am) ([A-Z][a-z]*)", "self_introduction", "first_name"),
        (r"(?i:they call me) ([A-Z][a-z]+)", "self_introduction", "nickname"),
        (r"(?i:everybody calls me) ([A-Z][a-z]+)", "self_introduction", "nickname"),
        (r"(?i:this is (?:my )?)(?:[a-z]+ )?([A-Z][a-z]+)", "third_party_introduction", "first_name"),
        (r"(?i:meet (?:my )?)(?:[a-z]+ )?([A-Z][a-z]+)", "third_party_introduction", "first_name"),
        (r"(?i:say hi to) ([A-Z][a-z]+)", "third_party_introduction", "first_name"),
        (r"(?i:this is (?:my )?)(?:[a-z]+ )?([A-Z][a-z]+)(?:(?:'s| the) ([A-Za-z]+))?", "third_party_introduction", "full_with_role"),
        (r"(?i:i'm) [A-Za-z]+,? (?:the |a )?([A-Za-z]+)", "self_introduction", "first_name_with_role"),
    ]
    results = []
    for pat, source, name_type in patterns:
        m = re.search(pat, text)
        if m:
            name = m.group(1)
            relationship = ""
            if "cousin" in text.lower() or "uncle" in text.lower() or "aunt" in text.lower() or "brother" in text.lower() or "sister" in text.lower():
                for rel in ["cousin", "uncle", "aunt", "brother", "sister", "friend", "colleague", "manager", "engineer"]:
                    if rel in text.lower():
                        relationship = rel
                        break
            results.append({
                "display_name": name,
                "source": source,
                "name_type": name_type,
                "relationship": relationship,
                "confidence": 0.85 if source == "self_introduction" else 0.7,
                "original_phrase": m.group(0),
                "full_text": text
            })
    # Deduplicate by display_name
    seen = set()
    unique = []
    for r in results:
        if r["display_name"] not in seen:
            seen.add(r["display_name"])
            unique.append(r)
    return {"version": "v752_introduction_trigger_parser", "created_at": datetime.now().isoformat(),
            "detections": unique, "detection_count": len(unique), "status": "ok"}


def main():
    import sys
    print(f"Nova v752_introduction_trigger_parser")
    r = introduction_trigger_parser()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
