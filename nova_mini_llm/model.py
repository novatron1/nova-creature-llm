import math
import torch
import torch.nn as nn
import torch.nn.functional as F


class MultiHeadSelfAttention(nn.Module):
    """
    Masked multi-head self-attention.

    This is the core "pay attention to earlier tokens" part.
    The mask stops the model from looking into the future.
    """
    def __init__(self, n_embd, n_heads, block_size, dropout):
        super().__init__()
        assert n_embd % n_heads == 0, "n_embd must divide evenly by n_heads"
        self.n_heads = n_heads
        self.head_dim = n_embd // n_heads

        self.qkv = nn.Linear(n_embd, 3 * n_embd)
        self.proj = nn.Linear(n_embd, n_embd)
        self.dropout = nn.Dropout(dropout)

        # Lower triangle mask: token can only see itself and earlier tokens.
        mask = torch.tril(torch.ones(block_size, block_size))
        self.register_buffer("mask", mask.view(1, 1, block_size, block_size))

    def forward(self, x):
        B, T, C = x.shape

        qkv = self.qkv(x)  # (B, T, 3C)
        q, k, v = qkv.chunk(3, dim=-1)

        # Split into heads.
        q = q.view(B, T, self.n_heads, self.head_dim).transpose(1, 2)
        k = k.view(B, T, self.n_heads, self.head_dim).transpose(1, 2)
        v = v.view(B, T, self.n_heads, self.head_dim).transpose(1, 2)

        # Attention scores.
        scores = (q @ k.transpose(-2, -1)) / math.sqrt(self.head_dim)

        # No peeking ahead.
        scores = scores.masked_fill(self.mask[:, :, :T, :T] == 0, float("-inf"))

        weights = F.softmax(scores, dim=-1)
        weights = self.dropout(weights)

        out = weights @ v  # (B, heads, T, head_dim)
        out = out.transpose(1, 2).contiguous().view(B, T, C)

        return self.proj(out)


class FeedForward(nn.Module):
    """
    The blue box in the Transformer diagram.

    After attention mixes information, this part thinks/processes each token.
    """
    def __init__(self, n_embd, dropout):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_embd, 4 * n_embd),
            nn.GELU(),
            nn.Linear(4 * n_embd, n_embd),
            nn.Dropout(dropout),
        )

    def forward(self, x):
        return self.net(x)


class Block(nn.Module):
    """
    One Transformer block:
    - Add & Norm
    - Masked Multi-Head Attention
    - Add & Norm
    - Feed Forward
    """
    def __init__(self, n_embd, n_heads, block_size, dropout):
        super().__init__()
        self.ln1 = nn.LayerNorm(n_embd)
        self.attn = MultiHeadSelfAttention(n_embd, n_heads, block_size, dropout)
        self.ln2 = nn.LayerNorm(n_embd)
        self.ff = FeedForward(n_embd, dropout)

    def forward(self, x):
        # Residual connection: x + attention(x)
        x = x + self.attn(self.ln1(x))
        # Residual connection: x + feed_forward(x)
        x = x + self.ff(self.ln2(x))
        return x


class GPTLanguageModel(nn.Module):
    """
    Tiny GPT-style decoder-only language model.

    This is the right side of the Transformer diagram:
    output embedding -> positional encoding -> masked attention blocks -> linear -> softmax.
    """
    def __init__(self, vocab_size, block_size=128, n_embd=128, n_heads=4, n_layers=4, dropout=0.1):
        super().__init__()
        self.block_size = block_size

        self.token_embedding = nn.Embedding(vocab_size, n_embd)
        self.position_embedding = nn.Embedding(block_size, n_embd)

        self.blocks = nn.Sequential(*[
            Block(n_embd, n_heads, block_size, dropout)
            for _ in range(n_layers)
        ])

        self.ln_f = nn.LayerNorm(n_embd)
        self.lm_head = nn.Linear(n_embd, vocab_size)

    def forward(self, idx, targets=None):
        B, T = idx.shape
        if T > self.block_size:
            raise ValueError(f"Sequence length {T} is bigger than block_size {self.block_size}")

        token_emb = self.token_embedding(idx)
        pos = torch.arange(T, device=idx.device)
        pos_emb = self.position_embedding(pos)

        x = token_emb + pos_emb
        x = self.blocks(x)
        x = self.ln_f(x)
        logits = self.lm_head(x)

        loss = None
        if targets is not None:
            B, T, C = logits.shape
            loss = F.cross_entropy(logits.view(B * T, C), targets.view(B * T))

        return logits, loss

    @torch.no_grad()
    def generate(self, idx, max_new_tokens=200, temperature=1.0, top_k=None):
        for _ in range(max_new_tokens):
            # Only feed the last block_size tokens.
            idx_cond = idx[:, -self.block_size:]

            logits, _ = self(idx_cond)
            logits = logits[:, -1, :] / temperature

            if top_k is not None:
                values, _ = torch.topk(logits, min(top_k, logits.size(-1)))
                logits[logits < values[:, [-1]]] = -float("inf")

            probs = F.softmax(logits, dim=-1)
            next_idx = torch.multinomial(probs, num_samples=1)
            idx = torch.cat((idx, next_idx), dim=1)

        return idx
