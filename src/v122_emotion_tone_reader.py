"""v122 — Emotion / Tone Reader."""
from __future__ import annotations
from datetime import datetime

PATTERNS = {"frustrated":["error","fail","broken","not working","why isn't"],
           "excited":["great","awesome","yes","perfect","amazing"],
           "confused":["what","huh","how","mean","unclear"],
           "urgent":["now","immediately","asap","hurry","critical"],
           "casual":["just","maybe","kinda","wonder"],
           "technical":["function","class","import","def __","pytest"]}

def detect_tone(text):
    text_lower = text.lower()
    scores = {tone: sum(1 for p in patterns if p in text_lower) for tone, patterns in PATTERNS.items()}
    detected = max(scores, key=scores.get) if max(scores.values()) > 0 else "neutral"
    return {"version":"v122_tone_reader","created_at":datetime.now().isoformat(),
            "text_sample":text[:50],"tone_scores":scores,"detected_tone":detected,
            "confidence":round(max(scores.values())/max(1,sum(scores.values()))*100,1) if sum(scores.values())>0 else 0,
            "note":"Tone appears/sounds like. Not claiming certainty."}

def main():
    print("Nova v122 -- Tone Reader\n")
    r = detect_tone("This is awesome!")
    print(f"Tone: {r['detected_tone']}, Confidence: {r['confidence']}%")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
