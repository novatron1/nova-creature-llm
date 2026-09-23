import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.companion_768d_token_utils import encode_with_unknown_fallback


class CharacterPieceTokenizer:
    UNK = "<unk>"
    EOT = "<|endoftext|>"
    tokens = ["<unk>", "<|endoftext|>", " ", "a", "b", "c", "d", "e", "-", "."]

    def encode(self, text: str) -> list[int]:
        if text == "cab":
            return [0]
        if any(character not in self.tokens for character in text):
            return [0]
        return [self.tokens.index(character) if character in self.tokens else 0 for character in text]


def test_unknown_word_is_rescued_with_known_character_pieces():
    ids, report = encode_with_unknown_fallback("cab", CharacterPieceTokenizer())

    assert ids == [5, 3, 4]
    assert report == {
        "original_unknown_count": 1,
        "rescued_count": 1,
        "unresolved_count": 0,
        "used_fallback": True,
    }


def test_known_text_is_not_retokenized():
    tokenizer = CharacterPieceTokenizer()

    ids, report = encode_with_unknown_fallback("a b", tokenizer)

    assert ids == [3, 2, 4]
    assert report["original_unknown_count"] == 0
    assert report["used_fallback"] is False


def test_unrepresentable_unknown_is_reported_without_inventing_an_id():
    ids, report = encode_with_unknown_fallback("cab?", CharacterPieceTokenizer())

    assert ids == [0]
    assert report == {
        "original_unknown_count": 1,
        "rescued_count": 0,
        "unresolved_count": 1,
        "used_fallback": False,
    }
