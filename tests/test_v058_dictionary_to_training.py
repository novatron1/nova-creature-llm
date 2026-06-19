from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dictionary_to_training import classify_role

def test_role_classifier():
    assert classify_role("What is 12 times 12?", "144.") == "left_hemisphere"
    assert classify_role("Who created you?", "Mr. Novotron.") == "memory_transformer"
    assert classify_role("What is my favorite color?", "I do not know.") == "critic_conscience_transformer"
