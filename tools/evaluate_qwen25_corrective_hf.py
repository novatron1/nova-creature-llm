"""Evaluate the unmerged corrective LoRA locally with Transformers.

This isolates adapter quality from GGUF conversion and Ollama registration.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path(r"F:\AI\models\Qwen2.5-1.5B-Instruct"),
    )
    parser.add_argument(
        "--adapter-dir",
        type=Path,
        default=Path(
            r"F:\AI\adapters\nova-qwen2.5-1.5b-corrective-candidate-20260723"
        ),
    )
    parser.add_argument(
        "--merged-model-dir",
        type=Path,
        default=None,
        help="Evaluate an already merged model instead of applying the LoRA at runtime.",
    )
    parser.add_argument(
        "--eval-file",
        type=Path,
        default=Path(
            r"C:\Users\nova\Documents\NOVA LLM CREATURE DESKTOP"
            r"\artifacts\nova_qwen25_corrective_20260723\corrective_eval.json"
        ),
    )
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--max-new-tokens", type=int, default=120)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            r"F:\AI\artifacts\nova-qwen2.5-1.5b-corrective-candidate-20260723"
            r"\local_hf_adapter_eval.json"
        ),
    )
    args = parser.parse_args()

    model_source = args.merged_model_dir or args.base_dir
    tokenizer_source = args.merged_model_dir or args.adapter_dir
    tokenizer = AutoTokenizer.from_pretrained(
        str(tokenizer_source), local_files_only=True, trust_remote_code=True
    )
    base = AutoModelForCausalLM.from_pretrained(
        str(model_source),
        local_files_only=True,
        dtype=torch.float16,
        device_map={"": "cpu"},
        low_cpu_mem_usage=True,
        trust_remote_code=True,
    )
    model = (
        base
        if args.merged_model_dir
        else PeftModel.from_pretrained(
            base, str(args.adapter_dir), local_files_only=True
        )
    )
    model.eval()

    cases = json.loads(args.eval_file.read_text(encoding="utf-8"))[: args.limit]
    results = []
    for case in cases:
        prompt = tokenizer.apply_chat_template(
            case["messages"], tokenize=False, add_generation_prompt=True
        )
        encoded = tokenizer(prompt, return_tensors="pt")
        started = time.perf_counter()
        with torch.no_grad():
            output = model.generate(
                **encoded,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                repetition_penalty=1.15,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        elapsed = time.perf_counter() - started
        generated = output[0][encoded["input_ids"].shape[1] :]
        response = tokenizer.decode(generated, skip_special_tokens=True).strip()
        lowered = response.lower()
        expected_pass = any(
            str(value).lower() in lowered for value in case.get("expected", [])
        )
        forbidden_pass = not any(
            str(value).lower() in lowered for value in case.get("forbidden", [])
        )
        result = {
            "name": case["name"],
            "response": response,
            "expected_pass": expected_pass,
            "forbidden_pass": forbidden_pass,
            "passed": expected_pass and forbidden_pass,
            "seconds": round(elapsed, 3),
        }
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)

    report = {
        "passed": sum(bool(item["passed"]) for item in results),
        "total": len(results),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"passed": report["passed"], "total": report["total"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
