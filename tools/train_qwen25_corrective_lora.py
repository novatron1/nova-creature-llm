from __future__ import annotations

import argparse
import inspect
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
DEFAULT_DATASET_DIR = "artifacts/nova_qwen25_corrective_20260723"
DEFAULT_OUTPUT_DIR = "/kaggle/working/nova_qwen25_corrective_adapter_20260723"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def validate_dataset(dataset_dir: Path) -> dict[str, Any]:
    problems: list[str] = []
    counts: dict[str, int] = {}
    prompt_sets: dict[str, set[str]] = {}
    for split in ("train", "validation", "holdout"):
        rows = read_jsonl(dataset_dir / f"{split}.jsonl")
        counts[split] = len(rows)
        prompt_sets[split] = set()
        for index, row in enumerate(rows):
            messages = row.get("messages")
            if not isinstance(messages, list) or len(messages) < 2:
                problems.append(f"{split}:{index}:bad_messages")
                continue
            if str(messages[-1].get("role", "")).lower() != "assistant":
                problems.append(f"{split}:{index}:last_message_not_assistant")
            if not str(messages[-1].get("content", "")).strip():
                problems.append(f"{split}:{index}:empty_assistant")
            prompt_sets[split].add(
                " ".join(str(row.get("prompt", "")).lower().split())
            )
    overlap = {
        "train_validation": len(prompt_sets["train"] & prompt_sets["validation"]),
        "train_holdout": len(prompt_sets["train"] & prompt_sets["holdout"]),
        "validation_holdout": len(prompt_sets["validation"] & prompt_sets["holdout"]),
    }
    if any(overlap.values()):
        problems.append(f"prompt_split_overlap:{overlap}")
    if not counts.get("train"):
        problems.append("empty_train")
    if not counts.get("validation"):
        problems.append("empty_validation")
    return {
        "counts": counts,
        "prompt_overlap": overlap,
        "problem_count": len(problems),
        "problems": problems[:50],
    }


def import_training_stack():
    import torch
    from datasets import Dataset
    from peft import (
        LoraConfig,
        PeftModel,
        TaskType,
        get_peft_model,
        prepare_model_for_kbit_training,
    )
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        EarlyStoppingCallback,
        Trainer,
        TrainingArguments,
    )

    return {
        "torch": torch,
        "Dataset": Dataset,
        "LoraConfig": LoraConfig,
        "PeftModel": PeftModel,
        "TaskType": TaskType,
        "get_peft_model": get_peft_model,
        "prepare_model_for_kbit_training": prepare_model_for_kbit_training,
        "AutoModelForCausalLM": AutoModelForCausalLM,
        "AutoTokenizer": AutoTokenizer,
        "BitsAndBytesConfig": BitsAndBytesConfig,
        "EarlyStoppingCallback": EarlyStoppingCallback,
        "Trainer": Trainer,
        "TrainingArguments": TrainingArguments,
    }


def encode_assistant_only(
    row: dict[str, Any],
    tokenizer,
    *,
    max_seq_length: int,
) -> dict[str, list[int]]:
    messages = row["messages"]
    if str(messages[-1].get("role", "")).lower() != "assistant":
        raise ValueError("Every training row must end with an assistant message.")

    full_ids = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=False,
    )
    prefix_ids = tokenizer.apply_chat_template(
        messages[:-1],
        tokenize=True,
        add_generation_prompt=True,
    )
    if isinstance(full_ids, dict) or hasattr(full_ids, "keys"):
        full_ids = full_ids["input_ids"]
    if isinstance(prefix_ids, dict) or hasattr(prefix_ids, "keys"):
        prefix_ids = prefix_ids["input_ids"]
    if hasattr(full_ids, "tolist"):
        full_ids = full_ids.tolist()
    if hasattr(prefix_ids, "tolist"):
        prefix_ids = prefix_ids.tolist()
    if full_ids and isinstance(full_ids[0], list):
        full_ids = full_ids[0]
    if prefix_ids and isinstance(prefix_ids[0], list):
        prefix_ids = prefix_ids[0]
    full_ids = list(full_ids)
    prefix_ids = list(prefix_ids)

    if full_ids[: len(prefix_ids)] != prefix_ids:
        raise ValueError(
            "The chat template prefix does not align with the complete conversation. "
            "Assistant-only loss cannot be guaranteed."
        )

    answer_start = len(prefix_ids)
    if len(full_ids) > max_seq_length:
        excess = len(full_ids) - max_seq_length
        removable_prefix = max(0, answer_start - 8)
        trim_left = min(excess, removable_prefix)
        if trim_left:
            full_ids = full_ids[trim_left:]
            answer_start -= trim_left
        if len(full_ids) > max_seq_length:
            full_ids = full_ids[:max_seq_length]

    if answer_start >= len(full_ids):
        raise ValueError("The assistant answer was fully truncated.")

    labels = [-100] * answer_start + full_ids[answer_start:]
    if not any(label != -100 for label in labels):
        raise ValueError("No assistant tokens remain after masking.")
    return {
        "input_ids": full_ids,
        "attention_mask": [1] * len(full_ids),
        "labels": labels,
    }


@dataclass
class AssistantOnlyCollator:
    tokenizer: Any
    pad_to_multiple_of: int = 8

    def __call__(self, features: list[dict[str, list[int]]]):
        import torch

        max_length = max(len(feature["input_ids"]) for feature in features)
        if self.pad_to_multiple_of:
            remainder = max_length % self.pad_to_multiple_of
            if remainder:
                max_length += self.pad_to_multiple_of - remainder

        input_ids: list[list[int]] = []
        attention_mask: list[list[int]] = []
        labels: list[list[int]] = []
        pad_id = int(self.tokenizer.pad_token_id)
        for feature in features:
            padding = max_length - len(feature["input_ids"])
            input_ids.append(feature["input_ids"] + [pad_id] * padding)
            attention_mask.append(feature["attention_mask"] + [0] * padding)
            labels.append(feature["labels"] + [-100] * padding)
        return {
            "input_ids": torch.tensor(input_ids, dtype=torch.long),
            "attention_mask": torch.tensor(attention_mask, dtype=torch.long),
            "labels": torch.tensor(labels, dtype=torch.long),
        }


def training_arguments_kwargs(args, stack: dict[str, Any], has_eval: bool) -> dict[str, Any]:
    values: dict[str, Any] = {
        "output_dir": str(Path(args.output_dir).resolve()),
        "num_train_epochs": args.epochs,
        "per_device_train_batch_size": args.batch_size,
        "per_device_eval_batch_size": 1,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "learning_rate": args.learning_rate,
        "logging_steps": 10,
        "save_steps": args.save_steps,
        "save_total_limit": 2,
        "warmup_ratio": 0.05,
        "lr_scheduler_type": "cosine",
        "report_to": "none",
        "fp16": True,
        "gradient_checkpointing": True,
        "remove_unused_columns": False,
        "load_best_model_at_end": bool(has_eval),
        "metric_for_best_model": "eval_loss",
        "greater_is_better": False,
        "seed": args.seed,
        "data_seed": args.seed,
    }
    if has_eval:
        signature = inspect.signature(stack["TrainingArguments"].__init__)
        strategy_name = (
            "eval_strategy" if "eval_strategy" in signature.parameters else "evaluation_strategy"
        )
        values[strategy_name] = "steps"
        values["eval_steps"] = args.eval_steps
        values["save_strategy"] = "steps"
    return values


def run_smoke_eval(model, tokenizer, eval_path: Path, torch, max_new_tokens: int) -> list[dict[str, Any]]:
    if not eval_path.exists():
        return []
    cases = json.loads(eval_path.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    model.eval()
    for case in cases:
        prompt = tokenizer.apply_chat_template(
            case["messages"],
            tokenize=False,
            add_generation_prompt=True,
        )
        encoded = tokenizer(prompt, return_tensors="pt")
        device = next(model.parameters()).device
        encoded = {key: value.to(device) for key, value in encoded.items()}
        with torch.no_grad():
            output = model.generate(
                **encoded,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                repetition_penalty=1.15,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        generated = output[0][encoded["input_ids"].shape[1] :]
        response = tokenizer.decode(generated, skip_special_tokens=True).strip()
        lower = response.lower()
        expected = [str(value) for value in case.get("expected", [])]
        forbidden = [str(value) for value in case.get("forbidden", [])]
        expected_pass = not expected or any(value.lower() in lower for value in expected)
        forbidden_pass = not any(value.lower() in lower for value in forbidden)
        results.append(
            {
                "name": case["name"],
                "response": response,
                "expected_pass": expected_pass,
                "forbidden_pass": forbidden_pass,
                "passed": expected_pass and forbidden_pass,
            }
        )
    return results


def train(args: argparse.Namespace) -> dict[str, Any]:
    stack = import_training_stack()
    torch = stack["torch"]
    project_root = Path(args.project_root).resolve()
    dataset_dir = (project_root / args.dataset_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    validation = validate_dataset(dataset_dir)
    if validation["problem_count"]:
        raise ValueError(f"Dataset validation failed: {validation['problems'][:5]}")

    tokenizer = stack["AutoTokenizer"].from_pretrained(
        args.base_model,
        trust_remote_code=True,
        use_fast=True,
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    train_rows = read_jsonl(dataset_dir / "train.jsonl")
    eval_rows = read_jsonl(dataset_dir / "validation.jsonl")[: args.max_eval_records]
    encode = lambda row: encode_assistant_only(
        row,
        tokenizer,
        max_seq_length=args.max_seq_length,
    )
    train_ds = stack["Dataset"].from_list([encode(row) for row in train_rows])
    eval_ds = stack["Dataset"].from_list([encode(row) for row in eval_rows])

    quant_config = None
    if args.use_4bit:
        quant_config = stack["BitsAndBytesConfig"](
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
        )
    model_kwargs: dict[str, Any] = {
        "trust_remote_code": True,
        "device_map": "auto",
    }
    if quant_config is not None:
        model_kwargs["quantization_config"] = quant_config
    else:
        model_kwargs["torch_dtype"] = torch.float16 if torch.cuda.is_available() else torch.float32
    model = stack["AutoModelForCausalLM"].from_pretrained(args.base_model, **model_kwargs)
    model.config.use_cache = False
    if args.use_4bit:
        model = stack["prepare_model_for_kbit_training"](model)

    resume_adapter = str(args.resume_adapter_dir or "").strip()
    if resume_adapter:
        model = stack["PeftModel"].from_pretrained(
            model,
            resume_adapter,
            is_trainable=True,
        )
    else:
        config = stack["LoraConfig"](
            task_type=stack["TaskType"].CAUSAL_LM,
            inference_mode=False,
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=args.lora_dropout,
            bias="none",
            target_modules=args.target_modules,
        )
        model = stack["get_peft_model"](model, config)
    model.print_trainable_parameters()

    training_args = stack["TrainingArguments"](
        **training_arguments_kwargs(args, stack, has_eval=bool(eval_rows))
    )
    callbacks = (
        [stack["EarlyStoppingCallback"](early_stopping_patience=args.early_stopping_patience)]
        if eval_rows
        else []
    )
    trainer = stack["Trainer"](
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        data_collator=AssistantOnlyCollator(tokenizer),
        callbacks=callbacks,
    )
    train_result = trainer.train()
    eval_metrics = trainer.evaluate()
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)

    smoke_results = run_smoke_eval(
        trainer.model,
        tokenizer,
        dataset_dir / "corrective_eval.json",
        torch,
        args.smoke_max_new_tokens,
    )
    smoke_summary = {
        "passed": sum(bool(row["passed"]) for row in smoke_results),
        "total": len(smoke_results),
        "results": smoke_results,
    }
    (output_dir / "corrective_smoke_eval.json").write_text(
        json.dumps(smoke_summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    assistant_tokens = sum(
        sum(label != -100 for label in row["labels"])
        for row in train_ds
    )
    total_tokens = sum(len(row["input_ids"]) for row in train_ds)
    metadata = {
        "training_kind": args.training_kind,
        "base_model": args.base_model,
        "dataset_dir": str(dataset_dir),
        "dataset_validation": validation,
        "output_dir": str(output_dir),
        "cuda_available": bool(torch.cuda.is_available()),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "epochs_requested": args.epochs,
        "learning_rate": args.learning_rate,
        "max_seq_length": args.max_seq_length,
        "lora_r": args.lora_r,
        "lora_alpha": args.lora_alpha,
        "lora_dropout": args.lora_dropout,
        "target_modules": args.target_modules,
        "use_4bit": args.use_4bit,
        "resume_adapter_dir": resume_adapter,
        "assistant_only_loss": True,
        "assistant_training_tokens": assistant_tokens,
        "total_sequence_tokens": total_tokens,
        "train_metrics": train_result.metrics,
        "eval_metrics": eval_metrics,
        "smoke_eval": {
            "passed": smoke_summary["passed"],
            "total": smoke_summary["total"],
        },
    }
    (output_dir / "nova_corrective_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )
    archive_path = shutil.make_archive(
        str(output_dir.parent / args.result_zip_name),
        "zip",
        output_dir,
    )
    metadata["result_zip"] = archive_path
    return metadata


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Train Nova Qwen2.5 1.5B with assistant-only corrective QLoRA."
    )
    value.add_argument("--project-root", default=".")
    value.add_argument("--dataset-dir", default=DEFAULT_DATASET_DIR)
    value.add_argument("--base-model", default=DEFAULT_BASE_MODEL)
    value.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    value.add_argument("--resume-adapter-dir", default="")
    value.add_argument("--max-seq-length", type=int, default=768)
    value.add_argument("--max-eval-records", type=int, default=160)
    value.add_argument("--epochs", type=float, default=2.0)
    value.add_argument("--batch-size", type=int, default=1)
    value.add_argument("--gradient-accumulation-steps", type=int, default=8)
    value.add_argument("--learning-rate", type=float, default=1e-4)
    value.add_argument("--lora-r", type=int, default=16)
    value.add_argument("--lora-alpha", type=int, default=32)
    value.add_argument("--lora-dropout", type=float, default=0.05)
    value.add_argument("--target-modules", default="all-linear")
    value.add_argument("--save-steps", type=int, default=50)
    value.add_argument("--eval-steps", type=int, default=50)
    value.add_argument("--early-stopping-patience", type=int, default=3)
    value.add_argument("--seed", type=int, default=20260723)
    value.add_argument("--smoke-max-new-tokens", type=int, default=120)
    value.add_argument(
        "--training-kind",
        default="nova_qwen25_corrective_assistant_only_sft",
    )
    value.add_argument(
        "--result-zip-name",
        default="nova_qwen25_corrective_lora_result_20260723",
    )
    value.add_argument(
        "--use-4bit",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    value.add_argument("--dry-run", action="store_true")
    return value


def main() -> int:
    args = parser().parse_args()
    dataset_dir = (Path(args.project_root).resolve() / args.dataset_dir).resolve()
    validation = validate_dataset(dataset_dir)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "dataset_dir": str(dataset_dir),
                    "base_model": args.base_model,
                    "output_dir": args.output_dir,
                    "assistant_only_loss": True,
                    "validation": validation,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1 if validation["problem_count"] else 0
    print(json.dumps(train(args), indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
