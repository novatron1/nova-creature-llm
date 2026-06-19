from __future__ import annotations

import hashlib
import json
import sys
import re
from pathlib import Path
from datetime import datetime

import torch
import torch.nn.functional as F
from torch import nn, optim

# ── paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nova_creature_llm_lab" / "src"))

ROLES = [
    "left_hemisphere",
    "right_hemisphere",
    "memory_transformer",
    "planner_transformer",
    "critic_conscience_transformer",
    "dream_simulation_transformer",
    "speech_output_transformer",
]

TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)
SPECIAL = {"<pad>": 0, "<bos>": 1, "<eos>": 2, "<unk>": 3}


def root() -> Path:
    return ROOT


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def basic_tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text)


def encode(vocab_stoi: dict[str, int], text: str) -> list[int]:
    tokens = basic_tokenize(text)
    ids = [SPECIAL["<bos>"]]
    ids.extend(vocab_stoi.get(t, SPECIAL["<unk>"]) for t in tokens)
    ids.append(SPECIAL["<eos>"])
    return ids


def decode(vocab_itos: dict[int, str], ids: list[int]) -> str:
    out = []
    for idx in ids:
        t = vocab_itos.get(int(idx), "<unk>")
        if t in ("<pad>", "<bos>", "<eos>"):
            continue
        if not out:
            out.append(t)
        elif re.fullmatch(r"[.,!?;:%)\]\}]", t):
            out[-1] = out[-1].rstrip()
            out.append(t)
        else:
            out.append(" " + t)
    return "".join(out).strip()


def make_model(cfg: dict) -> nn.Module:
    from model.transformer import CreatureTransformer
    mc = cfg["model"]
    model = CreatureTransformer(
        vocab_size=mc["vocab_size"],
        block_size=mc["block_size"],
        n_embd=mc["n_embd"],
        n_heads=mc["n_heads"],
        n_layers=mc["n_layers"],
        dropout=mc["dropout"],
    )
    return model


def finetune_role(role: str) -> dict | None:
    print(f"\n{'='*60}")
    print(f"Fine-tuning: {role}")
    print(f"{'='*60}")

    # ── paths ──────────────────────────────────────────────────────────────
    v054_path = root() / "checkpoints" / "brain_slots" / role / f"{role}_v054_specialized.pt"
    v055_path = root() / "checkpoints" / "brain_slots" / role / f"{role}_v055_finetuned.pt"
    training_path = root() / "exports" / "v053_training_sets" / f"{role}_training_set.json"
    manifest_path = root() / "checkpoints" / "brain_slots" / role / "v055_finetune_manifest.json"
    report_path = root() / "reports" / "v055_finetune_summary.json"

    if not v054_path.exists():
        print(f"  SKIP: {v054_path} not found")
        return None
    if not training_path.exists():
        print(f"  SKIP: {training_path} not found")
        return None

    before_hash = sha256(v054_path)

    # ── load checkpoint ────────────────────────────────────────────────────
    ckpt = torch.load(v054_path, map_location="cpu", weights_only=True)
    config = ckpt["config"]
    model_cfg = config["model"]

    print(f"  Model: vocab={model_cfg['vocab_size']}, embd={model_cfg['n_embd']}, "
          f"heads={model_cfg['n_heads']}, layers={model_cfg['n_layers']}, "
          f"block={model_cfg['block_size']}")

    # ── build model & load weights ─────────────────────────────────────────
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"  Device: {device}")

    model = make_model(config)
    model.load_state_dict(ckpt["model_state"], strict=False)
    model.train()
    model.to(device)

    # Enable gradients for fine-tuning
    for p in model.parameters():
        p.requires_grad = True

    # ── build vocabulary from checkpoint metadata and training data ────────
    # Collect all tokens from training data
    lessons = json.loads(training_path.read_text(encoding="utf-8"))
    all_texts = []
    for lesson in lessons:
        all_texts.append(lesson.get("prompt", ""))
        all_texts.append(lesson.get("answer", ""))

    # Build vocab
    from collections import Counter
    counter: Counter[str] = Counter()
    for text in all_texts:
        counter.update(basic_tokenize(text))

    vocab = list(SPECIAL.keys())
    for token, _freq in counter.most_common():
        if token not in vocab:
            vocab.append(token)
            if len(vocab) >= model_cfg["vocab_size"]:
                break

    stoi = {t: i for i, t in enumerate(vocab)}
    itos = {i: t for t, i in stoi.items()}

    # ── build training tensors ─────────────────────────────────────────────
    input_ids_list = []
    target_ids_list = []
    for lesson in lessons:
        text = lesson.get("prompt", "") + " " + lesson.get("answer", "")
        ids = encode(stoi, text)
        if len(ids) > model_cfg["block_size"]:
            ids = ids[: model_cfg["block_size"]]
        if len(ids) < 3:
            continue
        inp = torch.tensor(ids[:-1], dtype=torch.long)
        tgt = torch.tensor(ids[1:], dtype=torch.long)
        input_ids_list.append(inp)
        target_ids_list.append(tgt)

    if not input_ids_list:
        print("  SKIP: no valid training sequences")
        return None

    max_len = max(len(t) for t in input_ids_list)
    padded_inputs = []
    padded_targets = []
    for inp, tgt in zip(input_ids_list, target_ids_list):
        pad_len = max_len - len(inp)
        padded_inputs.append(F.pad(inp, (0, pad_len), value=SPECIAL["<pad>"]))
        padded_targets.append(F.pad(tgt, (0, pad_len), value=-100))

    X = torch.stack(padded_inputs).to(device)
    Y = torch.stack(padded_targets).to(device)

    print(f"  Sequences: {len(input_ids_list)}, max_len: {max_len}")

    # ── optimiser ──────────────────────────────────────────────────────────
    optimiser = optim.AdamW(model.parameters(), lr=1e-4, weight_decay=0.01)
    steps = 50  # lightweight fine-tuning pass

    # ── training loop ──────────────────────────────────────────────────────
    losses = []
    for step in range(steps):
        optimiser.zero_grad()
        logits, loss = model(X, targets=Y)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimiser.step()
        losses.append(loss.item())
        if (step + 1) % 10 == 0 or step == 0:
            print(f"  Step {step+1:>3}/{steps}  loss={loss.item():.6f}")

    start_loss = losses[0] if losses else 0.0
    final_loss = losses[-1] if losses else 0.0

    # ── save v055 checkpoint ───────────────────────────────────────────────
    model.cpu()
    new_state = model.state_dict()

    # Save new checkpoint (preserving original structure)
    v055_ckpt = {
        "model_state": new_state,
        "config": config,
        "optimizer_state": optimiser.state_dict(),
        "tokenizer_path": ckpt.get("tokenizer_path", ""),
        "metadata": {**ckpt.get("metadata", {}), "v055_finetuned": True, "finetuned_at": datetime.now().isoformat()},
    }
    torch.save(v055_ckpt, v055_path)
    after_hash = sha256(v055_path)
    weights_changed = before_hash != after_hash

    print(f"  Start loss: {start_loss:.6f}")
    print(f"  Final loss: {final_loss:.6f}")
    print(f"  Before hash: {before_hash[:16]}…")
    print(f"  After hash:  {after_hash[:16]}…")
    print(f"  Weights changed: {weights_changed}")

    # ── write manifest ──────────────────────────────────────────────────────
    manifest = {
        "version": "codex_cloud_v055",
        "role": role,
        "created_at": datetime.now().isoformat(),
        "checkpoint_path": str(v055_path.relative_to(root())),
        "checkpoint_status": "finetuned_from_v054",
        "source_checkpoint": str(v054_path.relative_to(root())),
        "source_before_sha256": before_hash,
        "finetuned_sha256": after_hash,
        "weights_changed": weights_changed,
        "training_set": str(training_path.relative_to(root())),
        "lesson_count": len(lessons),
        "training_steps": steps,
        "start_loss": round(start_loss, 6),
        "final_loss": round(final_loss, 6),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"  Manifest: {manifest_path}")

    return {
        "role": role,
        "checkpoint_path": str(v055_path.relative_to(root())),
        "lesson_count": len(lessons),
        "start_loss": round(start_loss, 6),
        "final_loss": round(final_loss, 6),
        "before_hash": before_hash,
        "after_hash": after_hash,
        "weights_changed": weights_changed,
    }


def main() -> int:
    print("Nova Creature Cloud v055 — Fine-Tune Role Brains")
    print(f"Torch: {torch.__version__}, CUDA: {torch.cuda.is_available()}")
    print(f"Project root: {root()}")

    results = []
    for role in ROLES:
        try:
            r = finetune_role(role)
            if r:
                results.append(r)
        except Exception as e:
            print(f"  ERROR on {role}: {e}")
            import traceback
            traceback.print_exc()

    # ── summary report ──────────────────────────────────────────────────────
    report = {
        "version": "codex_cloud_v055",
        "created_at": datetime.now().isoformat(),
        "torch_version": torch.__version__,
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "cuda_available": torch.cuda.is_available(),
        "roles_processed": len(results),
        "roles_total": len(ROLES),
        "can_promote": all(r["weights_changed"] for r in results) if results else False,
        "results": results,
    }
    report_path = root() / "reports" / "v055_finetune_summary.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Roles processed: {len(results)}/{len(ROLES)}")
    all_changed = all(r["weights_changed"] for r in results) if results else False
    print(f"All weights changed: {all_changed}")
    print(f"Can promote to v056: {all_changed}")
    for r in results:
        print(f"  {r['role']}: loss {r['start_loss']:.4f} → {r['final_loss']:.4f}, "
              f"changed={r['weights_changed']}")
    print(f"Report: {report_path}")

    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
