import argparse
import json
from pathlib import Path

import torch

from model import GPTLanguageModel


def build_vocab(text):
    chars = sorted(list(set(text)))
    stoi = {ch: i for i, ch in enumerate(chars)}
    itos = {i: ch for ch, i in stoi.items()}
    return chars, stoi, itos


def encode(text, stoi):
    return [stoi[ch] for ch in text]


def get_batch(data, block_size, batch_size, device):
    ix = torch.randint(len(data) - block_size - 1, (batch_size,))
    x = torch.stack([data[i:i + block_size] for i in ix])
    y = torch.stack([data[i + 1:i + block_size + 1] for i in ix])
    return x.to(device), y.to(device)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, default="data.txt")
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--block_size", type=int, default=128)
    parser.add_argument("--n_embd", type=int, default=128)
    parser.add_argument("--n_heads", type=int, default=4)
    parser.add_argument("--n_layers", type=int, default=4)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--out", type=str, default="nova_mini_llm.pt")
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")

    text = Path(args.data).read_text(encoding="utf-8")
    if len(text) < args.block_size + 2:
        raise ValueError("Training text is too small. Add more text or lower --block_size.")

    chars, stoi, itos = build_vocab(text)
    vocab_size = len(chars)
    print(f"Text length: {len(text)} characters")
    print(f"Vocabulary size: {vocab_size}")

    encoded = torch.tensor(encode(text, stoi), dtype=torch.long)

    # Simple split.
    n = int(0.9 * len(encoded))
    train_data = encoded[:n]
    val_data = encoded[n:]

    model = GPTLanguageModel(
        vocab_size=vocab_size,
        block_size=args.block_size,
        n_embd=args.n_embd,
        n_heads=args.n_heads,
        n_layers=args.n_layers,
        dropout=args.dropout,
    ).to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)

    @torch.no_grad()
    def estimate_loss():
        model.eval()
        losses = {}
        for split, split_data in [("train", train_data), ("val", val_data)]:
            batch_losses = []
            usable = split_data if len(split_data) > args.block_size + 1 else train_data
            for _ in range(10):
                xb, yb = get_batch(usable, args.block_size, args.batch_size, device)
                _, loss = model(xb, yb)
                batch_losses.append(loss.item())
            losses[split] = sum(batch_losses) / len(batch_losses)
        model.train()
        return losses

    for step in range(args.steps + 1):
        if step % 100 == 0:
            losses = estimate_loss()
            print(f"step {step}: train loss {losses['train']:.4f}, val loss {losses['val']:.4f}")

        xb, yb = get_batch(train_data, args.block_size, args.batch_size, device)
        _, loss = model(xb, yb)

        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()

    checkpoint = {
        "model_state": model.state_dict(),
        "config": {
            "vocab_size": vocab_size,
            "block_size": args.block_size,
            "n_embd": args.n_embd,
            "n_heads": args.n_heads,
            "n_layers": args.n_layers,
            "dropout": args.dropout,
        },
        "stoi": stoi,
        "itos": itos,
    }

    torch.save(checkpoint, args.out)
    print(f"Saved model to {args.out}")


if __name__ == "__main__":
    main()
