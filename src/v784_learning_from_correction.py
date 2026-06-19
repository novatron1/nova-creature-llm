"""v784_learning_from_correction — Rapid Education Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def learning_from_correction(correction_text="", original_claim=""):
    """Auto-create correction lesson when user corrects Nova."""
    now = datetime.now().isoformat()
    patterns = [
        r"(?i:no,? that'?s wrong,? it should be) (.+)",
        r"(?i:remember it like this) (.+)",
        r"(?i:from now on,? when i say .+? it means) (.+)",
        r"(?i:that person'?s name is actually) (.+)",
        r"(?i:actually,? .+?is) (.+)",
        r"(?i:it'?s not .+?,? it'?s) (.+)",
    ]
    corrected_fact = None
    for p in patterns:
        m = re.search(p, correction_text)
        if m:
            corrected_fact = m.group(1).strip()
            break
    if not corrected_fact:
        corrected_fact = f"User corrected: {correction_text[:100]}"
    lesson_id = f"cor_ls_{uuid.uuid4().hex[:6]}"
    lesson = {
        "lesson_id": lesson_id,
        "source": "user_correction",
        "topic": correction_text.split()[0].lower() if correction_text else "correction",
        "claim": corrected_fact,
        "original_claim": original_claim or "",
        "correction_text": correction_text,
        "explanation": f"Auto-created from user correction: {correction_text[:200]}",
        "examples": [],
        "tags": ["correction"],
        "confidence": 0.9,
        "created_at": now,
        "status": "pending"
    }
    return {"version": "v784_learning_from_correction", "created_at": now,
            "lesson": lesson, "correction_detected": corrected_fact is not None, "status": "ok"}


def main():
    print(f"Nova v784_learning_from_correction")
    r = learning_from_correction()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
