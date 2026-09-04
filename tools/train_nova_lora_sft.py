from __future__ import annotations

import argparse
import inspect
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
DEFAULT_DATASET_DIR = "artifacts/nova_large_sft_dataset"
DEFAULT_OUTPUT_DIR = "/kaggle/working/nova_lora_adapter"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if isinstance(item, dict):
            rows.append(item)
    return rows


def load_dataset_records(dataset_dir: Path, max_train_records: int = 0) -> dict[str, list[dict[str, Any]]]:
    train = read_jsonl(dataset_dir / "train.jsonl")
    validation = read_jsonl(dataset_dir / "validation.jsonl")
    holdout = read_jsonl(dataset_dir / "holdout.jsonl")
    if max_train_records and max_train_records > 0:
        train = train[:max_train_records]
    return {"train": train, "validation": validation, "holdout": holdout}


def format_chat_text(messages: list[dict[str, str]], tokenizer=None) -> str:
    if tokenizer is not None and hasattr(tokenizer, "apply_chat_template"):
        try:
            return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
        except Exception:
            pass

    role_labels = {"system": "System", "user": "User", "assistant": "Nova Creature"}
    lines = []
    for message in messages:
        role = role_labels.get(str(message.get("role", "")).lower(), "Message")
        content = str(message.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines).strip()


def validate_records(records: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    required = {"messages", "prompt", "response", "category"}
    counts = {split: len(rows) for split, rows in records.items()}
    categories: dict[str, int] = {}
    problems: list[str] = []
    for split, rows in records.items():
        for index, row in enumerate(rows):
            missing = required - set(row)
            if missing:
                problems.append(f"{split}:{index}:missing:{','.join(sorted(missing))}")
                continue
            messages = row.get("messages")
            if not isinstance(messages, list) or not messages or messages[-1].get("role") != "assistant":
                problems.append(f"{split}:{index}:bad_messages")
            category = str(row.get("category") or "unknown")
            categories[category] = categories.get(category, 0) + 1
    return {
        "counts": counts,
        "category_counts": dict(sorted(categories.items())),
        "problem_count": len(problems),
        "problems": problems[:25],
    }


def _training_arguments_kwargs(args, output_dir: Path, has_validation: bool) -> dict[str, Any]:
    kwargs = {
        "output_dir": str(output_dir),
        "num_train_epochs": args.epochs,
        "per_device_train_batch_size": args.batch_size,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "learning_rate": args.learning_rate,
        "logging_steps": 10,
        "save_steps": args.save_steps,
        "save_total_limit": 2,
        "warmup_ratio": 0.03,
        "lr_scheduler_type": "cosine",
        "report_to": "none",
        "fp16": True,
        "gradient_checkpointing": True,
        "remove_unused_columns": False,
    }
    if has_validation:
        signature = inspect.signature(_import_transformers()[3].__init__)
        if "eval_strategy" in signature.parameters:
            kwargs["eval_strategy"] = "steps"
        else:
            kwargs["evaluation_strategy"] = "steps"
        kwargs["eval_steps"] = args.eval_steps
    return kwargs


def _import_transformers():
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        DataCollatorForLanguageModeling,
        TrainingArguments,
    )

    return AutoModelForCausalLM, AutoTokenizer, DataCollatorForLanguageModeling, TrainingArguments


def _import_peft():
    from peft import LoraConfig, PeftModel, TaskType, get_peft_model, prepare_model_for_kbit_training

    return LoraConfig, PeftModel, TaskType, get_peft_model, prepare_model_for_kbit_training


def _maybe_quant_config(use_4bit: bool):
    if not use_4bit:
        return None
    import torch
    from transformers import BitsAndBytesConfig

    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
    )


def train_lora_sft(args) -> dict[str, Any]:
    import torch
    from datasets import Dataset
    from transformers import Trainer

    AutoModelForCausalLM, AutoTokenizer, DataCollatorForLanguageModeling, TrainingArguments = _import_transformers()
    LoraConfig, PeftModel, TaskType, get_peft_model, prepare_model_for_kbit_training = _import_peft()

    project_root = Path(args.project_root).resolve()
    dataset_dir = project_root / args.dataset_dir
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    records = load_dataset_records(dataset_dir, args.max_train_records)
    validation = validate_records(records)
    if validation["problem_count"]:
        raise ValueError(f"Dataset has schema problems: {validation['problems'][:3]}")
    if not records["train"]:
        raise ValueError(f"No training records found in {dataset_dir}")

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    def to_text_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
        return [{"text": format_chat_text(row["messages"], tokenizer=tokenizer)} for row in rows]

    train_ds = Dataset.from_list(to_text_rows(records["train"]))
    eval_rows = records["validation"][: max(args.max_eval_records, 1)]
    eval_ds = Dataset.from_list(to_text_rows(eval_rows)) if eval_rows else None

    def tokenize(batch):
        return tokenizer(batch["text"], max_length=args.max_seq_length, truncation=True, padding=False)

    tokenized_train = train_ds.map(tokenize, batched=True, remove_columns=["text"])
    tokenized_eval = eval_ds.map(tokenize, batched=True, remove_columns=["text"]) if eval_ds is not None else None

    model_kwargs: dict[str, Any] = {
        "trust_remote_code": True,
        "device_map": "auto",
    }
    quant_config = _maybe_quant_config(args.use_4bit)
    if quant_config is not None:
        model_kwargs["quantization_config"] = quant_config
    else:
        model_kwargs["torch_dtype"] = torch.float16 if torch.cuda.is_available() else torch.float32

    model = AutoModelForCausalLM.from_pretrained(args.base_model, **model_kwargs)
    if args.use_4bit:
        model = prepare_model_for_kbit_training(model)

    resume_adapter_dir = str(getattr(args, "resume_adapter_dir", "") or "").strip()
    if resume_adapter_dir:
        model = PeftModel.from_pretrained(model, resume_adapter_dir, is_trainable=True)
    else:
        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            inference_mode=False,
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=args.lora_dropout,
            bias="none",
            target_modules=args.target_modules,
        )
        model = get_peft_model(model, lora_config)
    if hasattr(model, "print_trainable_parameters"):
        model.print_trainable_parameters()

    training_args = TrainingArguments(**_training_arguments_kwargs(args, output_dir, tokenized_eval is not None))
    collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_train,
        eval_dataset=tokenized_eval,
        data_collator=collator,
    )

    train_result = trainer.train()
    eval_metrics = trainer.evaluate() if tokenized_eval is not None else {}
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    metadata = {
        "base_model": args.base_model,
        "dataset_dir": str(dataset_dir),
        "output_dir": str(output_dir),
        "cuda_available": bool(torch.cuda.is_available()),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "train_records": len(records["train"]),
        "validation_records": len(records["validation"]),
        "holdout_records": len(records["holdout"]),
        "max_seq_length": args.max_seq_length,
        "epochs": args.epochs,
        "learning_rate": args.learning_rate,
        "lora_r": args.lora_r,
        "lora_alpha": args.lora_alpha,
        "lora_dropout": args.lora_dropout,
        "target_modules": args.target_modules,
        "use_4bit": args.use_4bit,
        "resume_adapter_dir": resume_adapter_dir,
        "train_metrics": getattr(train_result, "metrics", {}),
        "eval_metrics": eval_metrics,
        "dataset_validation": validation,
    }
    (output_dir / "nova_lora_metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    zip_base = output_dir.parent / "nova_lora_sft_result"
    archive_path = shutil.make_archive(str(zip_base), "zip", output_dir)
    metadata["result_zip"] = archive_path
    return metadata


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train a Nova LoRA adapter from the large Nova SFT dataset.")
    parser.add_argument("--project-root", default=".", help="Extracted Nova bundle root.")
    parser.add_argument("--dataset-dir", default=DEFAULT_DATASET_DIR, help="Dataset directory relative to project root.")
    parser.add_argument("--base-model", default=os.environ.get("NOVA_LORA_BASE_MODEL", DEFAULT_BASE_MODEL))
    parser.add_argument("--output-dir", default=os.environ.get("NOVA_LORA_OUTPUT_DIR", DEFAULT_OUTPUT_DIR))
    parser.add_argument("--max-train-records", type=int, default=int(os.environ.get("NOVA_MAX_TRAIN_RECORDS", "6000")))
    parser.add_argument("--max-eval-records", type=int, default=int(os.environ.get("NOVA_MAX_EVAL_RECORDS", "500")))
    parser.add_argument("--max-seq-length", type=int, default=int(os.environ.get("NOVA_MAX_SEQ_LENGTH", "1024")))
    parser.add_argument("--epochs", type=float, default=float(os.environ.get("NOVA_LORA_EPOCHS", "1")))
    parser.add_argument("--batch-size", type=int, default=int(os.environ.get("NOVA_LORA_BATCH_SIZE", "1")))
    parser.add_argument("--gradient-accumulation-steps", type=int, default=int(os.environ.get("NOVA_LORA_GRAD_ACCUM", "8")))
    parser.add_argument("--learning-rate", type=float, default=float(os.environ.get("NOVA_LORA_LR", "2e-4")))
    parser.add_argument("--lora-r", type=int, default=int(os.environ.get("NOVA_LORA_R", "16")))
    parser.add_argument("--lora-alpha", type=int, default=int(os.environ.get("NOVA_LORA_ALPHA", "32")))
    parser.add_argument("--lora-dropout", type=float, default=float(os.environ.get("NOVA_LORA_DROPOUT", "0.05")))
    parser.add_argument("--target-modules", default=os.environ.get("NOVA_LORA_TARGET_MODULES", "all-linear"))
    parser.add_argument("--resume-adapter-dir", default=os.environ.get("NOVA_LORA_RESUME_ADAPTER_DIR", ""))
    parser.add_argument("--save-steps", type=int, default=int(os.environ.get("NOVA_LORA_SAVE_STEPS", "200")))
    parser.add_argument("--eval-steps", type=int, default=int(os.environ.get("NOVA_LORA_EVAL_STEPS", "100")))
    parser.add_argument("--use-4bit", action=argparse.BooleanOptionalAction, default=os.environ.get("NOVA_LORA_USE_4BIT", "true").lower() != "false")
    parser.add_argument("--dry-run", action="store_true", help="Validate dataset and print config without importing training libraries.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    project_root = Path(args.project_root).resolve()
    dataset_dir = project_root / args.dataset_dir
    records = load_dataset_records(dataset_dir, args.max_train_records)
    validation = validate_records(records)
    dry_report = {
        "project_root": str(project_root),
        "dataset_dir": str(dataset_dir),
        "base_model": args.base_model,
        "output_dir": args.output_dir,
        "resume_adapter_dir": args.resume_adapter_dir,
        "max_train_records": args.max_train_records,
        "max_seq_length": args.max_seq_length,
        "use_4bit": args.use_4bit,
        "dataset_validation": validation,
    }
    if args.dry_run:
        print(json.dumps(dry_report, indent=2, sort_keys=True))
        return 1 if validation["problem_count"] or not records["train"] else 0

    metadata = train_lora_sft(args)
    print(json.dumps(metadata, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
