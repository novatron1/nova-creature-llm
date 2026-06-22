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
        byte_values = []
        for index, token_id in enumerate(token_ids):
            try:
                token_int = int(token_id)
            except (TypeError, ValueError) as exc:
                raise TypeError(f"unsupported token id at index {index}: {token_id!r}") from exc
            if self.BYTE_OFFSET <= token_int < self.vocab_size:
                byte_values.append(token_int - self.BYTE_OFFSET)
        return bytes(byte_values).decode("utf-8", errors="replace")

    def encode_pair(self, prompt: str, answer: str) -> tuple[list[int], list[int]]:
        return self.encode(prompt), self.encode(answer)
