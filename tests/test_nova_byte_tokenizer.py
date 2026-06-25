from pathlib import Path
import sys

import pytest

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


def test_decode_coerces_scalar_like_ids_and_ignores_out_of_range_tokens():
    tokenizer = NovaByteTokenizer()

    text = tokenizer.decode(
        [
            tokenizer.BOS,
            tokenizer.BYTE_OFFSET + ord("A"),
            str(tokenizer.BYTE_OFFSET + ord("B")),
            9999,
            -1,
            tokenizer.EOS,
        ]
    )

    assert text == "AB"


def test_decode_unsupported_token_objects_raise_clear_type_error():
    tokenizer = NovaByteTokenizer()

    with pytest.raises(TypeError, match="token id at index 1"):
        tokenizer.decode([tokenizer.BOS, object()])
