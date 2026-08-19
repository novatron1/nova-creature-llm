"""Merge a trained Qwen2.5 LoRA, convert it to GGUF, and register it in Ollama.

The candidate is installed under a separate Ollama name so the currently
installed Nova model is never replaced during evaluation.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


DEFAULT_ADAPTER = Path(r"F:\AI\adapters\nova-qwen2.5-1.5b-corrective-candidate-20260723")
DEFAULT_BASE = Path(r"F:\AI\models\Qwen2.5-1.5B-Instruct")
DEFAULT_OUTPUT = Path(r"F:\AI\artifacts\nova-qwen2.5-1.5b-corrective-candidate-20260723")
DEFAULT_CONVERTER = Path(r"F:\AI\tools\llama.cpp\convert_hf_to_gguf.py")
DEFAULT_QUANTIZER = Path(r"F:\AI\tools\llama-b10075-bin-win-cpu-x64\llama-quantize.exe")
DEFAULT_OLLAMA_MODEL = "nova-qwen2.5-1.5b-corrective-candidate"


def require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} was not found: {path}")


def require_dir(path: Path, label: str) -> None:
    if not path.is_dir():
        raise FileNotFoundError(f"{label} was not found: {path}")


def run(command: list[str]) -> None:
    print("RUN", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter-dir", type=Path, default=DEFAULT_ADAPTER)
    parser.add_argument("--base-dir", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--converter", type=Path, default=DEFAULT_CONVERTER)
    parser.add_argument("--quantizer", type=Path, default=DEFAULT_QUANTIZER)
    parser.add_argument("--ollama-model", default=DEFAULT_OLLAMA_MODEL)
    parser.add_argument("--quantization", default="Q4_K_M")
    parser.add_argument("--skip-merge", action="store_true")
    parser.add_argument("--skip-convert", action="store_true")
    parser.add_argument("--skip-quantize", action="store_true")
    parser.add_argument("--skip-register", action="store_true")
    args = parser.parse_args()

    adapter_dir = args.adapter_dir.resolve()
    base_dir = args.base_dir.resolve()
    output_dir = args.output_dir.resolve()
    merged_dir = output_dir / "merged_hf"
    f16_gguf = output_dir / "nova-qwen2.5-1.5b-corrective-f16.gguf"
    quantized_gguf = output_dir / (
        f"nova-qwen2.5-1.5b-corrective-{args.quantization}.gguf"
    )
    modelfile = output_dir / "Modelfile"
    report_path = output_dir / "build_report.json"

    require_dir(adapter_dir, "Adapter directory")
    require_file(adapter_dir / "adapter_config.json", "Adapter configuration")
    require_file(adapter_dir / "adapter_model.safetensors", "Adapter weights")
    require_dir(base_dir, "Local Qwen base model")
    require_file(base_dir / "model.safetensors", "Local Qwen base weights")
    require_file(args.converter.resolve(), "llama.cpp converter")
    require_file(args.quantizer.resolve(), "llama.cpp quantizer")
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_merge:
        print("Loading the original Qwen2.5 1.5B model from local storage...", flush=True)
        tokenizer = AutoTokenizer.from_pretrained(
            str(adapter_dir), local_files_only=True, trust_remote_code=True
        )
        base = AutoModelForCausalLM.from_pretrained(
            str(base_dir),
            local_files_only=True,
            dtype=torch.float16,
            device_map={"": "cpu"},
            low_cpu_mem_usage=True,
            trust_remote_code=True,
        )
        print("Applying and permanently merging the corrective LoRA...", flush=True)
        model = PeftModel.from_pretrained(base, str(adapter_dir), local_files_only=True)
        model = model.merge_and_unload(safe_merge=True)
        merged_dir.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(
            str(merged_dir), safe_serialization=True, max_shard_size="4GB"
        )
        tokenizer.save_pretrained(str(merged_dir))
        del model, base
        print("MERGE_COMPLETE", merged_dir, flush=True)

    if not args.skip_convert:
        require_dir(merged_dir, "Merged Hugging Face model")
        run(
            [
                str(Path(__import__("sys").executable)),
                str(args.converter.resolve()),
                str(merged_dir),
                "--outfile",
                str(f16_gguf),
                "--outtype",
                "f16",
            ]
        )

    if not args.skip_quantize:
        require_file(f16_gguf, "F16 GGUF")
        run(
            [
                str(args.quantizer.resolve()),
                str(f16_gguf),
                str(quantized_gguf),
                args.quantization,
            ]
        )

    modelfile.write_text(
        "\n".join(
            [
                f'FROM "{quantized_gguf}"',
                "",
                "PARAMETER temperature 0.55",
                "PARAMETER top_p 0.9",
                "PARAMETER num_ctx 8192",
                "",
            ]
        ),
        encoding="utf-8",
    )

    if not args.skip_register:
        require_file(quantized_gguf, "Quantized GGUF")
        run(["ollama", "create", args.ollama_model, "-f", str(modelfile)])

    report = {
        "ok": True,
        "adapter_dir": str(adapter_dir),
        "base_dir": str(base_dir),
        "merged_dir": str(merged_dir),
        "f16_gguf": str(f16_gguf),
        "quantized_gguf": str(quantized_gguf),
        "quantization": args.quantization,
        "ollama_model": args.ollama_model,
        "registered": not args.skip_register,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
