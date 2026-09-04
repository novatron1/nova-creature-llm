from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ADAPTER_ID = "nova-dolphin3-llama3-1-8b-full-sft-20260712"
DEFAULT_ADAPTER_DIR = ROOT / "models" / "lora_adapters" / DEFAULT_ADAPTER_ID
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "dolphin_lora_ollama"
DEFAULT_BASE_MODEL = "dphn/Dolphin3.0-Llama3.1-8B"
DEFAULT_OLLAMA_MODEL = "nova-dolphin3-lora"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _quote(value: str | Path) -> str:
    return shlex.quote(str(value))


def _validate_adapter_dir(adapter_dir: Path) -> None:
    missing = []
    for name in ("adapter_config.json", "nova_lora_metadata.json"):
        if not (adapter_dir / name).exists():
            missing.append(name)
    if not any((adapter_dir / name).exists() for name in ("adapter_model.safetensors", "adapter_model.bin")):
        missing.append("adapter_model.safetensors or adapter_model.bin")
    if missing:
        raise FileNotFoundError("Missing Dolphin LoRA adapter file(s): " + ", ".join(missing))


def _write_merge_script(path: Path, *, adapter_dir: Path, merged_dir: Path, base_model: str) -> None:
    script = f'''from pathlib import Path
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE_MODEL = {base_model!r}
ADAPTER_DIR = Path({str(adapter_dir)!r})
MERGED_DIR = Path({str(merged_dir)!r})
MERGED_DIR.mkdir(parents=True, exist_ok=True)

print("Loading base model:", BASE_MODEL)
tokenizer = AutoTokenizer.from_pretrained(str(ADAPTER_DIR), trust_remote_code=True)
base = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    torch_dtype=torch.float16,
    device_map="auto",
    low_cpu_mem_usage=True,
    trust_remote_code=True,
)
print("Loading adapter:", ADAPTER_DIR)
model = PeftModel.from_pretrained(base, str(ADAPTER_DIR))
print("Merging adapter into base model...")
model = model.merge_and_unload()
print("Saving merged model:", MERGED_DIR)
model.save_pretrained(str(MERGED_DIR), safe_serialization=True)
tokenizer.save_pretrained(str(MERGED_DIR))
print("MERGE_DONE", MERGED_DIR)
'''
    path.write_text(script, encoding="utf-8")


def _write_modelfile(path: Path, *, gguf_path: Path, ollama_model: str) -> None:
    content = f'''FROM {gguf_path}

PARAMETER temperature 0.55
PARAMETER top_p 0.9
PARAMETER num_ctx 8192

# Create with:
# ollama create {ollama_model} -f {path}
'''
    path.write_text(content, encoding="utf-8")


def prepare_conversion_plan(
    *,
    adapter_dir: str | Path = DEFAULT_ADAPTER_DIR,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    base_model: str | None = None,
    ollama_model: str = DEFAULT_OLLAMA_MODEL,
    quantization: str = "Q4_K_M",
    llama_cpp_dir: str | Path | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    adapter_path = Path(adapter_dir).resolve()
    output_path = Path(output_dir).resolve()
    _validate_adapter_dir(adapter_path)

    adapter_config = _read_json(adapter_path / "adapter_config.json")
    metadata = _read_json(adapter_path / "nova_lora_metadata.json")
    selected_base_model = str(
        base_model
        or metadata.get("base_model")
        or adapter_config.get("base_model_name_or_path")
        or DEFAULT_BASE_MODEL
    )

    output_path.mkdir(parents=True, exist_ok=True)
    merged_dir = output_path / "merged_hf"
    merge_script = output_path / "merge_dolphin_lora.py"
    gguf_f16 = output_path / "nova-dolphin3-lora-f16.gguf"
    gguf_quantized = output_path / f"nova-dolphin3-lora-{quantization}.gguf"
    modelfile = output_path / "Modelfile"
    llama_cpp_path = Path(llama_cpp_dir).resolve() if llama_cpp_dir else ROOT / "tools" / "llama.cpp"
    convert_script = llama_cpp_path / "convert_hf_to_gguf.py"
    quantize_name = "llama-quantize.exe" if os.name == "nt" else "llama-quantize"
    quantize_bin = llama_cpp_path / "build" / "bin" / quantize_name
    python_exe = Path(sys.executable).resolve() if sys.executable else "python"

    _write_merge_script(merge_script, adapter_dir=adapter_path, merged_dir=merged_dir, base_model=selected_base_model)
    _write_modelfile(modelfile, gguf_path=gguf_quantized, ollama_model=ollama_model)

    commands = [
        f"{_quote(python_exe)} {_quote(merge_script)}",
        f"{_quote(python_exe)} {_quote(convert_script)} {_quote(merged_dir)} --outfile {_quote(gguf_f16)} --outtype f16",
        f"{_quote(quantize_bin)} {_quote(gguf_f16)} {_quote(gguf_quantized)} {quantization}",
        f"ollama create {ollama_model} -f {_quote(modelfile)}",
    ]
    report = {
        "ok": True,
        "dry_run": bool(dry_run),
        "adapter_dir": str(adapter_path),
        "base_model": selected_base_model,
        "metadata_train_records": metadata.get("train_records"),
        "metadata_eval_loss": (metadata.get("eval_metrics") or {}).get("eval_loss"),
        "output_dir": str(output_path),
        "merged_dir": str(merged_dir),
        "merge_script": str(merge_script),
        "gguf_f16": str(gguf_f16),
        "gguf_quantized": str(gguf_quantized),
        "modelfile": str(modelfile),
        "ollama_model": ollama_model,
        "llama_cpp_dir": str(llama_cpp_path),
        "commands": commands,
    }
    (output_path / "conversion_plan.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if not dry_run:
        for command in commands:
            subprocess.run(command, cwd=str(ROOT), shell=True, check=True)
        report["executed"] = True
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare or execute Dolphin LoRA -> merged HF -> GGUF -> Ollama conversion.")
    parser.add_argument("--adapter-dir", default=str(DEFAULT_ADAPTER_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--base-model", default="")
    parser.add_argument("--ollama-model", default=DEFAULT_OLLAMA_MODEL)
    parser.add_argument("--quantization", default="Q4_K_M")
    parser.add_argument("--llama-cpp-dir", default="")
    parser.add_argument("--execute", action="store_true", help="Actually run merge, convert, quantize, and ollama create commands.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = prepare_conversion_plan(
        adapter_dir=args.adapter_dir,
        output_dir=args.output_dir,
        base_model=args.base_model or None,
        ollama_model=args.ollama_model,
        quantization=args.quantization,
        llama_cpp_dir=args.llama_cpp_dir or None,
        dry_run=not args.execute,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
