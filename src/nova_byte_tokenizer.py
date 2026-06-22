class NovaByteTokenizer:
    PAD = 0
    BOS = 1
    EOS = 2
    SEP = 3
    BYTE_OFFSET = 4
    vocab_size = 260

    def encode(self, text: str, *, add_special: bool = True) -> list[int]:
        token_ids = [byte + self.BYTE_OFFSET for byte in text.encode("utf-8")]
        if add_special:
            return [self.BOS, *token_ids, self.EOS]
        return token_ids

    def decode(self, token_ids: list[int]) -> str:
        byte_values = [
            token_id - self.BYTE_OFFSET
            for token_id in token_ids
            if self.BYTE_OFFSET <= token_id < self.vocab_size
        ]
        return bytes(byte_values).decode("utf-8", errors="replace")

    def encode_pair(self, prompt: str, answer: str) -> tuple[list[int], list[int]]:
        return self.encode(prompt), self.encode(answer)
