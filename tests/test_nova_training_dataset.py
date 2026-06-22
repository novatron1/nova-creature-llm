from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_training_dataset import clean_record, grouped_split


def test_recursive_followup_is_quarantined():
    record = {
        "user": "yeah",
        "nova": "I recall your last question. I recall your last question. More?",
        "source": "conversation",
    }
    cleaned, reason = clean_record(record)
    assert cleaned is None
    assert reason == "recursive_followup"


def test_truncated_answer_is_quarantined():
    cleaned, reason = clean_record(
        {"prompt": "What is love?", "answer": "Love is a deep emotional bon", "source": "dictionary_hit"}
    )
    assert cleaned is None
    assert reason == "truncated_answer"


def test_paraphrase_group_never_crosses_splits():
    rows = [
        {"id": "1", "intent_group": "creator_identity", "prompt": "Who made you?", "answer": "Mr. Novotron."},
        {"id": "2", "intent_group": "creator_identity", "prompt": "Who created you?", "answer": "Mr. Novotron."},
        {"id": "3", "intent_group": "quadratic", "prompt": "Quadratic formula?", "answer": "x = (-b ± sqrt(b² - 4ac)) / (2a)."},
    ]
    splits = grouped_split(rows, seed=20260622)
    locations = {
        row["intent_group"]: split
        for split, values in splits.items()
        for row in values
    }
    assert sum(any(row["intent_group"] == "creator_identity" for row in values) for values in splits.values()) == 1
    assert set(splits) == {"train", "validation", "promotion"}
