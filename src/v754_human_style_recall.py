"""v754_human_style_recall — Natural People Memory Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re
ROOT = Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0, str(ROOT / "src"))

def human_style_recall(name=None, face_id=None, voice_id=None):
    """Recall a person naturally by name, face, or voice match."""
    db_path = ROOT / "data/people/profiles.jsonl"
    profiles = []
    if db_path.exists():
        with open(db_path) as f:
            for line in f:
                line = line.strip()
                if line: profiles.append(json.loads(line))
    matches = []
    for p in profiles:
        score = 0.0
        match_reasons = []
        if name and name.lower() in p.get("display_name", "").lower():
            score += 0.9
            match_reasons.append("name_match")
        if face_id and p.get("face_embedding_id") == face_id:
            score += 0.8
            match_reasons.append("face_match")
        if voice_id and p.get("voice_embedding_id") == voice_id:
            score += 0.75
            match_reasons.append("voice_match")
        if score > 0:
            matches.append({"person": p, "confidence": min(score, 1.0), "match_reasons": match_reasons})
    matches.sort(key=lambda x: x["confidence"], reverse=True)
    if not matches:
        return {"version": "v754_human_style_recall", "created_at": datetime.now().isoformat(),
                "recall": "I do not remember this person.", "confidence": 0.0,
                "matches": [], "status": "ok"}
    top = matches[0]
    if top["confidence"] >= 0.8:
        recall_text = f"I remember you as {top['person']['display_name']}."
    elif top["confidence"] >= 0.5:
        recall_text = f"I think this is {top['person']['display_name']}."
    else:
        recall_text = f"I might be mixing this up. Could this be {top['person']['display_name']}?"
    return {"version": "v754_human_style_recall", "created_at": datetime.now().isoformat(),
            "recall": recall_text, "confidence": top["confidence"],
            "top_match": top["person"]["display_name"],
            "matches": matches[:3], "status": "ok"}


def main():
    import sys
    print(f"Nova v754_human_style_recall")
    r = human_style_recall()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
