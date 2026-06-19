import argparse

import torch

from model import GPTLanguageModel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="nova_mini_llm.pt")
    parser.add_argument("--prompt", type=str, default="Nova")
    parser.add_argument("--max_new_tokens", type=int, default=300)
    parser.add_argument("--temperature", type=float, default=0.9)
    parser.add_argument("--top_k", type=int, default=30)
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"

    checkpoint = torch.load(args.model, map_location=device)
    config = checkpoint["config"]
    stoi = checkpoint["stoi"]
    itos = {int(k): v for k, v in checkpoint["itos"].items()} if isinstance(next(iter(checkpoint["itos"].keys())), str) else checkpoint["itos"]

    model = GPTLanguageModel(**config).to(device)
    model.load_state_dict(checkpoint["model_state"])
    model.eval()

    # Replace unknown prompt characters with space if available, else first vocab char.
    fallback = stoi.get(" ", 0)
    start_ids = [stoi.get(ch, fallback) for ch in args.prompt]
    idx = torch.tensor([start_ids], dtype=torch.long, device=device)

    out = model.generate(
        idx,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
        top_k=args.top_k,
    )[0].tolist()

    text = "".join(itos[i] for i in out)
    print(text)


if __name__ == "__main__":
    main()
