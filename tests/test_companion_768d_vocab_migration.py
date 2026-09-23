import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.companion_768d_vocab_migration import (
    copy_vocab_expanded_state,
    extend_tokenizer_state,
)


def test_tokenizer_extension_appends_only_new_tokens():
    state = {
        "type": "curated",
        "vocab_size": 4,
        "tokens": ["<unk>", "<|endoftext|>", "gravity", "mass"],
    }

    expanded = extend_tokenizer_state(state, ["gravity", "density", "surface"])

    assert expanded["tokens"] == ["<unk>", "<|endoftext|>", "gravity", "mass", "density", "surface"]
    assert expanded["vocab_size"] == 6
    assert state["tokens"] == ["<unk>", "<|endoftext|>", "gravity", "mass"]


def test_tokenizer_extension_rejects_special_tokens():
    state = {"type": "curated", "vocab_size": 2, "tokens": ["<unk>", "<|endoftext|>"]}

    with pytest.raises(ValueError, match="special"):
        extend_tokenizer_state(state, ["<unk>"])


def test_vocab_state_copy_preserves_all_old_rows():
    source = {
        "token_emb.weight": np.arange(8, dtype=np.float32).reshape(4, 2),
        "lm_head.weight": np.arange(8, dtype=np.float32).reshape(4, 2) + 10,
        "block.weight": np.ones((2, 2), dtype=np.float32),
    }
    target = {
        "token_emb.weight": np.full((6, 2), -1.0, dtype=np.float32),
        "lm_head.weight": np.full((6, 2), -2.0, dtype=np.float32),
        "block.weight": np.zeros((2, 2), dtype=np.float32),
    }

    migrated = copy_vocab_expanded_state(source, target, old_vocab=4)

    assert np.array_equal(migrated["token_emb.weight"][:4], source["token_emb.weight"])
    assert np.array_equal(migrated["lm_head.weight"][:4], source["lm_head.weight"])
    assert np.array_equal(migrated["block.weight"], source["block.weight"])
    assert np.array_equal(migrated["token_emb.weight"][4:], np.full((2, 2), -1.0))
    assert np.array_equal(migrated["lm_head.weight"][4:], np.full((2, 2), -2.0))
