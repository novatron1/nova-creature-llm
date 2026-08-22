"""Nova Companion 768d dictionary/concept continuation training for Kaggle.

This runner starts from a completed 768d checkpoint, restores its tokenizer,
mixes concept lessons with replay from the original corpus, and writes a new
resumable run. It never reuses the base run directory or base optimizer state.
"""

from __future__ import annotations

import glob
import inspect
import json
import math
import os
import random
import re
import signal
import sys
import time
from pathlib import Path

import torch
import torch.nn.functional as F
from torch.cuda.amp import GradScaler, autocast
from torch.utils.data import DataLoader, Dataset


DATA_ROOT = Path(
    os.environ.get(
        "NOVA_DATA_ROOT",
        "/kaggle/input/datasets/novatron513/mynova/kaggle_upload",
    )
)
CONCEPT_ROOT = Path(
    os.environ.get(
        "NOVA_CONCEPT_ROOT",
        str(DATA_ROOT / "concept_upgrade"),
    )
)
BASE_CHECKPOINT = Path(os.environ.get("NOVA_BASE_CHECKPOINT", ""))
RUN_DIR = Path(os.environ.get("NOVA_RUN_DIR", "/kaggle/working/companion_768d_concept_upgrade"))
RUN_DIR.mkdir(parents=True, exist_ok=True)

MAX_STEPS = int(os.environ.get("NOVA_MAX_STEPS", "8000"))
CHECKPOINT_EVERY = max(100, int(os.environ.get("NOVA_CHECKPOINT_EVERY", "500")))
KEEP_CHECKPOINTS = max(1, int(os.environ.get("NOVA_KEEP_CHECKPOINTS", "2")))
EVAL_INTERVAL = max(100, int(os.environ.get("NOVA_EVAL_INTERVAL", "500")))
CONCEPT_RATIO = float(os.environ.get("NOVA_CONCEPT_RATIO", "0.75"))
LR = float(os.environ.get("NOVA_LEARNING_RATE", "5e-5"))
BATCH_SIZE = int(os.environ.get("NOVA_BATCH_SIZE", "8"))
GRAD_ACCUM = int(os.environ.get("NOVA_GRAD_ACCUM", "8"))
MAX_SEQ_LEN = int(os.environ.get("NOVA_MAX_SEQ_LEN", "256"))
SEED = int(os.environ.get("NOVA_SEED", "7682026"))
UNK_POLICY = os.environ.get("NOVA_UNK_POLICY", "drop").lower()
LOSS_MASK_MODE = os.environ.get("NOVA_LOSS_MASK_MODE", "answer").lower()
VOCAB_MODE = os.environ.get("NOVA_VOCAB_MODE", "none").lower()
VOCAB_MAX_ADDITIONS = max(0, int(os.environ.get("NOVA_VOCAB_MAX_ADDITIONS", "2048")))

if not BASE_CHECKPOINT.is_file():
    raise FileNotFoundError(
        "NOVA_BASE_CHECKPOINT must point to the completed 768d checkpoint file. "
        f"Received: {BASE_CHECKPOINT}"
    )
if not 0 < CONCEPT_RATIO <= 1:
    raise ValueError("NOVA_CONCEPT_RATIO must be greater than 0 and at most 1")
if UNK_POLICY not in {"drop", "fail", "allow", "fallback"}:
    raise ValueError("NOVA_UNK_POLICY must be drop, fail, allow, or fallback")
if LOSS_MASK_MODE not in {"answer", "full"}:
    raise ValueError("NOVA_LOSS_MASK_MODE must be answer or full")
if VOCAB_MODE not in {"none", "concept_expand"}:
    raise ValueError("NOVA_VOCAB_MODE must be none or concept_expand")

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Device: {DEVICE}", flush=True)
if DEVICE == "cuda":
    print(f"GPU: {torch.cuda.get_device_name(0)}", flush=True)

sys.path.insert(0, str(DATA_ROOT))
sys.path.insert(0, str(CONCEPT_ROOT))
import hlm_intelligence as H  # noqa: E402
from companion_768d_token_utils import (  # noqa: E402
    build_loss_mask,
    encode_with_unknown_fallback,
    end_of_text_token_id,
    truncate_at_end_of_text,
    tokenize_documents_with_boundaries,
    unknown_token_id,
)
from companion_768d_vocab_migration import (  # noqa: E402
    copy_vocab_expanded_state,
    extend_tokenizer_state,
)


def _load_checkpoint(path: Path) -> dict:
    try:
        return torch.load(path, map_location=DEVICE, weights_only=False)
    except TypeError:
        return torch.load(path, map_location=DEVICE)


def _restore_tokenizer(tokenizer, state: dict):
    if not isinstance(state, dict):
        raise ValueError("Base checkpoint does not contain a tokenizer state dictionary")

    for method_name in ("load_ckpt_dict", "load_checkpoint_dict", "restore_ckpt_dict"):
        method = getattr(tokenizer, method_name, None)
        if callable(method):
            result = method(state)
            return result if result is not None else tokenizer

    for method_name in ("from_ckpt_dict", "from_checkpoint_dict"):
        method = getattr(type(tokenizer), method_name, None)
        if callable(method):
            result = method(state)
            if result is not None:
                return result

    copied = 0
    for key, value in state.items():
        if hasattr(tokenizer, key):
            setattr(tokenizer, key, value)
            copied += 1
    if copied == 0:
        raise ValueError(
            "Could not restore the tokenizer state: CuratedTokenizer exposes no "
            "compatible checkpoint restore method or fields."
        )
    return tokenizer


def _refresh_tokenizer_maps(tokenizer):
    tokens = list(getattr(tokenizer, "tokens", []) or [])
    if not tokens:
        raise ValueError("Restored tokenizer exposes no tokens")
    tokenizer.tokens = tokens
    tokenizer.vocab_size = len(tokens)
    tokenizer.stoi = {token: index for index, token in enumerate(tokens)}
    tokenizer.itos = {index: token for index, token in enumerate(tokens)}
    return tokenizer


def _config_from_checkpoint(checkpoint: dict, *, vocab_size: int | None = None):
    saved = dict(checkpoint.get("config") or {})
    if not saved:
        raise ValueError("Base checkpoint does not contain model configuration")
    if vocab_size is not None:
        saved["vocab_size"] = int(vocab_size)
    signature = inspect.signature(H.HierarchicalConfig)
    allowed = set(signature.parameters)
    config_values = {key: value for key, value in saved.items() if key in allowed}
    return H.HierarchicalConfig(**config_values)


def _read_documents_from_shards() -> list[str]:
    corpus_dir = DATA_ROOT / "corpus" / "companion_full"
    shards = sorted(corpus_dir.glob("shard_*.jsonl"))
    if not shards:
        raise FileNotFoundError(f"No base corpus shards found under {corpus_dir}")
    documents: list[str] = []
    for shard in shards:
        with shard.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                text = str(record.get("text") or "").strip()
                if text:
                    documents.append(text)
    if not documents:
        raise RuntimeError("Base corpus contains no text documents")
    return documents


def _read_concept_documents(name: str) -> list[str]:
    path = CONCEPT_ROOT / name
    if not path.is_file():
        raise FileNotFoundError(f"Concept artifact is missing: {path}")
    rows: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            text = str(row.get("text") or "").strip()
            if text:
                rows.append(text)
    if not rows:
        raise RuntimeError(f"Concept artifact contains no text: {path}")
    return rows


def _collect_missing_concept_tokens(documents: list[str], tokenizer) -> list[str]:
    tokenize = getattr(tokenizer, "_tokenize", None)
    known = set(getattr(tokenizer, "stoi", {}) or {})
    missing: set[str] = set()
    for text in documents:
        pieces = tokenize(text.lower()) if callable(tokenize) else re.findall(r"[a-z0-9]+(?:['-][a-z0-9]+)*|[^\w\s]", text.lower())
        for piece in pieces:
            if piece and piece not in known and piece not in {"<unk>", "<|endoftext|>"}:
                missing.add(piece)
    return sorted(missing)[:VOCAB_MAX_ADDITIONS]


def _unknown_id(tokenizer) -> int | None:
    return unknown_token_id(tokenizer)


_ENCODED_CACHE: dict[str, list[int]] = {}


def _encode_document(text: str, tokenizer) -> tuple[list[int], dict]:
    cached = _ENCODED_CACHE.get(text)
    if cached is not None:
        ids = list(cached)
        unk_id = _unknown_id(tokenizer)
        unresolved = ids.count(unk_id) if unk_id is not None else 0
        return ids, {
            "original_unknown_count": unresolved,
            "rescued_count": 0,
            "unresolved_count": unresolved,
            "used_fallback": False,
        }
    ids, rescue_report = encode_with_unknown_fallback(text, tokenizer)
    _ENCODED_CACHE[text] = list(ids)
    return ids, rescue_report


def _encode_documents(documents: list[str], tokenizer) -> tuple[list[str], dict]:
    unk_id = _unknown_id(tokenizer)
    kept: list[str] = []
    unknown_rows: list[dict] = []
    unknown_count = 0
    total_count = 0
    original_unknown_count = 0
    rescued_count = 0
    for index, text in enumerate(documents):
        ids, rescue_report = _encode_document(text, tokenizer)
        total_count += len(ids)
        original_unknown_count += int(rescue_report["original_unknown_count"])
        rescued_count += int(rescue_report["rescued_count"])
        row_unknown = ids.count(unk_id) if unk_id is not None else 0
        unknown_count += row_unknown
        if row_unknown:
            unknown_rows.append(
                {
                    "index": index,
                    "unknown_count": row_unknown,
                    "original_unknown_count": rescue_report["original_unknown_count"],
                    "text": text[:200],
                }
            )
            if UNK_POLICY == "drop":
                continue
            if UNK_POLICY == "fail":
                raise ValueError(f"Unknown token found in concept document {index}: {text[:200]}")
        kept.append(text)
    report = {
        "input_documents": len(documents),
        "kept_documents": len(kept),
        "dropped_documents": len(documents) - len(kept),
        "total_token_count": total_count,
        "original_unknown_token_count": original_unknown_count,
        "rescued_segment_count": rescued_count,
        "unknown_token_count": unknown_count,
        "unknown_rate": unknown_count / total_count if total_count else 0.0,
        "unknown_examples": unknown_rows[:20],
        "policy": UNK_POLICY,
    }
    return kept, report


def _mix_documents(concept: list[str], replay: list[str], ratio: float, seed: int) -> list[str]:
    if not concept:
        raise RuntimeError("No concept documents remain after tokenizer coverage filtering")
    rng = random.Random(seed)
    mixed = list(concept)
    replay_count = round(len(concept) * (1 - ratio) / ratio) if replay and ratio < 1 else 0
    for index in range(replay_count):
        mixed.append(replay[index % len(replay)])
    rng.shuffle(mixed)
    return mixed


def _tokenize_documents(documents: list[str], tokenizer) -> tuple[torch.Tensor, torch.Tensor]:
    values: list[int] = []
    loss_mask: list[int] = []
    for text in documents:
        ids, _ = _encode_document(text, tokenizer)
        mask = [1] * len(ids) if LOSS_MASK_MODE == "full" else build_loss_mask(
            text, tokenizer, encoded_ids=ids
        )
        if len(ids) != len(mask):
            raise ValueError("Tokenizer loss mask length does not match encoded document length")
        values.extend(ids)
        loss_mask.extend(mask)
        values.append(end_of_text_token_id(tokenizer))
        loss_mask.append(1)
    if not values:
        raise RuntimeError("The tokenizer produced zero tokens")
    return torch.tensor(values, dtype=torch.long), torch.tensor(loss_mask, dtype=torch.float32)


checkpoint = _load_checkpoint(BASE_CHECKPOINT)
saved_tokenizer = checkpoint.get("tokenizer")
tokenizer = H.CuratedTokenizer(vocab_size=5000)
tokenizer = _refresh_tokenizer_maps(_restore_tokenizer(tokenizer, saved_tokenizer))
base_vocab = int((checkpoint.get("config") or {}).get("vocab_size", tokenizer.vocab_size))

base_documents = _read_documents_from_shards()
concept_train_raw = _read_concept_documents("train.jsonl")
concept_validation_raw = _read_concept_documents("validation.jsonl")
vocab_additions: list[str] = []
if VOCAB_MODE == "concept_expand":
    vocab_additions = _collect_missing_concept_tokens(concept_train_raw + concept_validation_raw, tokenizer)
    expanded_tokenizer_state = extend_tokenizer_state(tokenizer.ckpt_dict(), vocab_additions)
    tokenizer = H.CuratedTokenizer(vocab_size=expanded_tokenizer_state["vocab_size"])
    tokenizer = _refresh_tokenizer_maps(_restore_tokenizer(tokenizer, expanded_tokenizer_state))

config = _config_from_checkpoint(checkpoint, vocab_size=int(tokenizer.vocab_size))
expected_vocab = int(getattr(config, "vocab_size", getattr(tokenizer, "vocab_size", 0)))
if int(tokenizer.vocab_size) != expected_vocab:
    raise ValueError(
        f"Tokenizer/model mismatch: tokenizer={tokenizer.vocab_size}, model={expected_vocab}"
    )
print(f"Tokenizer restored: {tokenizer.vocab_size} tokens", flush=True)
print(
    json.dumps(
        {
            "vocab_mode": VOCAB_MODE,
            "base_vocab": base_vocab,
            "expanded_vocab": int(tokenizer.vocab_size),
            "vocab_addition_count": len(vocab_additions),
            "vocab_additions": vocab_additions[:50],
        }
    ),
    flush=True,
)
concept_train, train_coverage = _encode_documents(concept_train_raw, tokenizer)
concept_validation, validation_coverage = _encode_documents(concept_validation_raw, tokenizer)
if not concept_validation:
    concept_validation = concept_train[: max(1, min(32, len(concept_train)))]

split_at = max(1, int(len(base_documents) * 0.95))
base_train = base_documents[:split_at]
base_validation = base_documents[split_at:]
train_documents = _mix_documents(concept_train, base_train, CONCEPT_RATIO, SEED)
validation_documents = _mix_documents(
    concept_validation,
    base_validation or base_train[: max(1, min(64, len(base_train)))],
    CONCEPT_RATIO,
    SEED + 1,
)
print(json.dumps({"train_coverage": train_coverage, "validation_coverage": validation_coverage}, indent=2), flush=True)

train_ids, train_loss_mask = _tokenize_documents(train_documents, tokenizer)
validation_ids, validation_loss_mask = _tokenize_documents(validation_documents, tokenizer)
print(
    f"Concept documents: train={len(concept_train):,} validation={len(concept_validation):,} | "
    f"Tokens: train={len(train_ids):,} validation={len(validation_ids):,}",
    flush=True,
)

model = H.HierarchicalLM(config).to(DEVICE)
if int(tokenizer.vocab_size) == base_vocab:
    model.load_state_dict(checkpoint["model"])
else:
    migrated_state = copy_vocab_expanded_state(checkpoint["model"], model.state_dict(), old_vocab=base_vocab)
    model.load_state_dict(migrated_state)
print(f"Loaded base checkpoint: {BASE_CHECKPOINT}", flush=True)
print(f"Model: {model.count_parameters() / 1e6:.2f}M params", flush=True)

optimizer = torch.optim.AdamW(model.parameters(), lr=LR, betas=(0.9, 0.95), weight_decay=0.1)
scaler = GradScaler(enabled=(DEVICE == "cuda"))
use_amp = DEVICE == "cuda"


def get_lr(step: int) -> float:
    warmup = min(500, max(1, MAX_STEPS // 8))
    if step < warmup:
        return LR * step / warmup
    return LR * 0.5 * (1 + math.cos(math.pi * (step - warmup) / max(1, MAX_STEPS - warmup)))


class TokenDataset(Dataset):
    def __init__(self, values: torch.Tensor, loss_mask: torch.Tensor, seq_len: int):
        self.values = values
        self.loss_mask = loss_mask
        self.seq_len = seq_len

    def __len__(self) -> int:
        return max(0, len(self.values) - self.seq_len - 1)

    def __getitem__(self, index: int):
        return (
            self.values[index : index + self.seq_len],
            self.values[index + 1 : index + self.seq_len + 1],
            self.loss_mask[index + 1 : index + self.seq_len + 1],
        )


train_loader = DataLoader(
    TokenDataset(train_ids, train_loss_mask, MAX_SEQ_LEN),
    batch_size=BATCH_SIZE,
    shuffle=True,
    drop_last=True,
)


def _atomic_torch_save(payload: dict, target: Path) -> None:
    temporary = target.with_suffix(target.suffix + ".tmp")
    torch.save(payload, temporary)
    os.replace(temporary, target)


def _rng_state() -> dict:
    state = {"python": random.getstate(), "torch": torch.get_rng_state()}
    if DEVICE == "cuda":
        state["cuda"] = torch.cuda.get_rng_state_all()
    return state


def _checkpoint_payload(step: int, best_val: float) -> dict:
    return {
        "model": model.state_dict(),
        "optimizer": optimizer.state_dict(),
        "scaler": scaler.state_dict(),
        "step": int(step),
        "best_val": float(best_val),
        "config": H.asdict(config),
        "tokenizer": tokenizer.ckpt_dict(),
        "rng_state": _rng_state(),
        "base_checkpoint": str(BASE_CHECKPOINT),
        "concept_root": str(CONCEPT_ROOT),
        "vocab_expansion": {
            "mode": VOCAB_MODE,
            "base_vocab": base_vocab,
            "expanded_vocab": int(tokenizer.vocab_size),
            "additions": vocab_additions,
        },
        "concept_ratio": CONCEPT_RATIO,
        "unknown_token_report": {
            "train": train_coverage,
            "validation": validation_coverage,
        },
        "loss_mask_policy": "full_sequence" if LOSS_MASK_MODE == "full" else "answer_and_statement_spans_only",
        "max_steps": MAX_STEPS,
        "saved_at": time.time(),
    }


def _checkpoint_step(path: Path) -> int:
    try:
        return int(path.stem.split("_")[-1])
    except (ValueError, IndexError):
        return -1


def _latest_checkpoint() -> Path | None:
    paths = [Path(path) for path in glob.glob(str(RUN_DIR / "checkpoint_*.pt"))]
    return max(paths, key=_checkpoint_step) if paths else None


def _prune_checkpoints() -> None:
    paths = sorted(
        (Path(path) for path in glob.glob(str(RUN_DIR / "checkpoint_*.pt"))),
        key=_checkpoint_step,
        reverse=True,
    )
    for old in paths[KEEP_CHECKPOINTS:]:
        old.unlink(missing_ok=True)


def save_checkpoint(step: int, best_val: float, reason: str) -> None:
    target = RUN_DIR / f"checkpoint_{step:06d}.pt"
    _atomic_torch_save(_checkpoint_payload(step, best_val), target)
    manifest = {
        "latest": target.name,
        "step": int(step),
        "best_val": float(best_val),
        "reason": reason,
        "base_checkpoint": str(BASE_CHECKPOINT),
        "saved_at": time.time(),
    }
    manifest_path = RUN_DIR / "latest_checkpoint.json"
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    os.replace(temporary, manifest_path)
    _prune_checkpoints()
    print(f"[checkpoint] saved {target.name} ({reason})", flush=True)


@torch.no_grad()
def evaluate() -> float:
    model.eval()
    dataset = TokenDataset(validation_ids, validation_loss_mask, MAX_SEQ_LEN)
    if len(dataset) < 1:
        return float("inf")
    losses = []
    for _ in range(min(20, max(1, len(dataset)))):
        index = random.randrange(len(dataset))
        x, y, target_mask = dataset[index]
        x = x.unsqueeze(0).to(DEVICE)
        y = y.unsqueeze(0).to(DEVICE)
        target_mask = target_mask.unsqueeze(0).to(DEVICE)
        with autocast(enabled=use_amp):
            logits = model(x)["logits"]
        token_losses = F.cross_entropy(
            logits.reshape(-1, tokenizer.vocab_size), y.reshape(-1), reduction="none"
        )
        weights = target_mask.reshape(-1)
        losses.append(((token_losses * weights).sum() / weights.sum().clamp_min(1.0)).item())
    model.train()
    return sum(losses) / len(losses)


@torch.no_grad()
def quick_test() -> None:
    model.eval()
    prompts = [
        "Question: What is gravity? Answer:",
        "Question: What is a planet related to? Answer:",
        "Question: If mass doubles and radius stays fixed, what happens to surface gravity? Answer:",
        "Question: What is density? Answer:",
    ]
    for prompt in prompts:
        prompt_ids = torch.tensor([tokenizer.encode(prompt)], dtype=torch.long, device=DEVICE)
        output = model.generate(prompt_ids, max_new_tokens=60, temperature=0.5, top_k=20)
        text = truncate_at_end_of_text(tokenizer.decode(output[0].tolist()), tokenizer)
        print(f"    [{prompt[:64]}...] -> {text[:180]}", flush=True)
    model.train()


stop_requested = False


def _request_stop(signum, _frame) -> None:
    global stop_requested
    stop_requested = True
    print(f"[signal] received {signum}; saving at the next safe point", flush=True)


signal.signal(signal.SIGINT, _request_stop)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, _request_stop)

random.seed(SEED)
torch.manual_seed(SEED)
if DEVICE == "cuda":
    torch.cuda.manual_seed_all(SEED)

step = 0
best_val = float("inf")
latest = _latest_checkpoint()
if latest is not None:
    print(
        "A checkpoint already exists in the upgrade run directory. "
        "This runner intentionally does not restore its optimizer; rerun with "
        "the same directory only to restart the upgrade from the base checkpoint.",
        flush=True,
    )

print(f"Training {MAX_STEPS} concept-upgrade steps; checkpoint every {CHECKPOINT_EVERY}", flush=True)
started = time.time()
model.train()
data_loader = iter(train_loader)
while step < MAX_STEPS and not stop_requested:
    try:
        batch_x, batch_y, batch_mask = next(data_loader)
    except StopIteration:
        data_loader = iter(train_loader)
        batch_x, batch_y, batch_mask = next(data_loader)
    step += 1
    for group in optimizer.param_groups:
        group["lr"] = get_lr(step)
    batch_x = batch_x.to(DEVICE)
    batch_y = batch_y.to(DEVICE)
    batch_mask = batch_mask.to(DEVICE)
    with autocast(enabled=use_amp):
        output = model(batch_x, return_hidden=True)
        logits = output["logits"]
        token_losses = F.cross_entropy(
            logits.reshape(-1, tokenizer.vocab_size), batch_y.reshape(-1), reduction="none"
        )
        weights = batch_mask.reshape(-1)
        loss = (token_losses * weights).sum() / weights.sum().clamp_min(1.0)
        loss = loss / GRAD_ACCUM
    scaler.scale(loss).backward()
    if step % GRAD_ACCUM == 0:
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        scaler.step(optimizer)
        scaler.update()
        optimizer.zero_grad(set_to_none=True)

    if step % 100 == 0:
        elapsed = time.time() - started
        remaining = max(0, MAX_STEPS - step)
        hours_left = (elapsed / max(1, step) * remaining) / 3600
        raw_loss = loss.item() * GRAD_ACCUM
        print(
            f"  Step {step:5d}/{MAX_STEPS} | Loss: {raw_loss:.4f} | "
            f"PPL: {math.exp(min(raw_loss, 20)):.1f} | ~{hours_left:.1f}h left",
            flush=True,
        )

    if step % CHECKPOINT_EVERY == 0:
        save_checkpoint(step, best_val, "periodic")
    if step % EVAL_INTERVAL == 0:
        val_loss = evaluate()
        print(f">>> VAL step {step} | Loss: {val_loss:.4f} | PPL: {math.exp(min(val_loss, 20)):.1f}", flush=True)
        if val_loss < best_val:
            best_val = val_loss
            _atomic_torch_save(
                {
                    "model": model.state_dict(),
                    "config": H.asdict(config),
                    "tokenizer": tokenizer.ckpt_dict(),
                    "step": step,
                    "val_loss": best_val,
                    "base_checkpoint": str(BASE_CHECKPOINT),
                    "vocab_expansion": {
                        "mode": VOCAB_MODE,
                        "base_vocab": base_vocab,
                        "expanded_vocab": int(tokenizer.vocab_size),
                        "additions": vocab_additions,
                    },
                    "concept_ratio": CONCEPT_RATIO,
                    "unknown_token_report": {"train": train_coverage, "validation": validation_coverage},
                    "loss_mask_policy": "full_sequence" if LOSS_MASK_MODE == "full" else "answer_and_statement_spans_only",
                },
                RUN_DIR / "best.pt",
            )
            print("    [saved best.pt]", flush=True)
        quick_test()

if stop_requested:
    save_checkpoint(step, best_val, "stop-signal")

final_payload = {
    "model": model.state_dict(),
    "config": H.asdict(config),
    "tokenizer": tokenizer.ckpt_dict(),
    "step": step,
    "best_val": best_val,
    "finished": step >= MAX_STEPS,
    "base_checkpoint": str(BASE_CHECKPOINT),
    "concept_root": str(CONCEPT_ROOT),
    "vocab_expansion": {
        "mode": VOCAB_MODE,
        "base_vocab": base_vocab,
        "expanded_vocab": int(tokenizer.vocab_size),
        "additions": vocab_additions,
    },
    "concept_ratio": CONCEPT_RATIO,
    "unknown_token_report": {"train": train_coverage, "validation": validation_coverage},
    "loss_mask_policy": "full_sequence" if LOSS_MASK_MODE == "full" else "answer_and_statement_spans_only",
    "saved_at": time.time(),
}
_atomic_torch_save(final_payload, RUN_DIR / "final.pt")
(RUN_DIR / "training_report.json").write_text(
    json.dumps(
        {
            "version": "companion_768d_concept_upgrade_v1",
            "step": step,
            "max_steps": MAX_STEPS,
            "best_val": best_val,
            "finished": step >= MAX_STEPS,
            "base_checkpoint": str(BASE_CHECKPOINT),
            "concept_root": str(CONCEPT_ROOT),
            "vocab_expansion": {
                "mode": VOCAB_MODE,
                "base_vocab": base_vocab,
                "expanded_vocab": int(tokenizer.vocab_size),
                "additions": vocab_additions,
            },
            "concept_ratio": CONCEPT_RATIO,
            "learning_rate": LR,
            "loss_mask_policy": "full_sequence" if LOSS_MASK_MODE == "full" else "answer_and_statement_spans_only",
            "unknown_token_report": {"train": train_coverage, "validation": validation_coverage},
            "run_dir": str(RUN_DIR),
        },
        indent=2,
    ),
    encoding="utf-8",
)
print(f"Saved final.pt at step {step}; finished={step >= MAX_STEPS}", flush=True)
print(f"Downloadable outputs are under {RUN_DIR}", flush=True)
