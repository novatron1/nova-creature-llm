"""v773_introduction_confidence_scorer — Natural People Memory Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re
ROOT = Path(__file__).resolve().parents[1]

def introduction_confidence_scorer(text="", source="self_introduction"):
    """Score confidence of an introduction detection."""
    score = 0.5
    factors = []
    if source == "self_introduction":
        score += 0.2
        factors.append("direct_intro")
    if any(w in text.lower() for w in ["my name is", "i'm", "i am"]):
        score += 0.2
        factors.append("clear_intro_phrase")
    if any(w in text.lower() for w in ["this is", "meet", "say hi"]):
        score += 0.1
        factors.append("third_party_intro")
    name_pattern = re.search(r"([A-Z][a-z]+)", text)
    if name_pattern:
        score += 0.1
        factors.append("capitalized_name")
    score = min(score, 1.0)
    return {"version": "v773_introduction_confidence_scorer", "created_at": datetime.now().isoformat(),
            "text": text, "source": source, "confidence": score, "factors": factors, "status": "ok"}


def main():
    import sys
    print(f"Nova v773_introduction_confidence_scorer")
    r = introduction_confidence_scorer()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
