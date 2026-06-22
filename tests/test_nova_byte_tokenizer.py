from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_byte_tokenizer import NovaByteTokenizer


def test_utf8_round_trip_has_no_unknown_tokens():
    tokenizer = NovaByteTokenizer()
    text = "Nova can debug Python — café 🚀"

    ids = tokenizer.encode(text)

    assert tokenizer.decode(ids) == text
    assert tokenizer.vocab_size == 260
    assert ids[0] == tokenizer.BOS
    assert ids[-1] == tokenizer.EOS


def test_answer_boundary_is_preserved():
    tokenizer = NovaByteTokenizer()

    prompt_ids, answer_ids = tokenizer.encode_pair("Question?", "Answer.")

    assert tokenizer.decode(prompt_ids) == "Question?"
    assert tokenizer.decode(answer_ids) == "Answer."
