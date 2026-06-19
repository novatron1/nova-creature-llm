from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dictionary_memory import DictionaryMemory

def test_dictionary_exact(tmp_path):
    d = DictionaryMemory(tmp_path)
    d.add_approved("What is the test answer?", "This is the answer.")
    hit = d.lookup("What is the test answer?")
    assert hit["found"] is True
    assert hit["answer"] == "This is the answer."
