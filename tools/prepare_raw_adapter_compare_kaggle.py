from __future__ import annotations

import argparse
import json
import shutil
import textwrap
import time
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADAPTER_ROOT = ROOT / "models" / "lora_adapters"
DEFAULT_OUT = ROOT / "artifacts"

QWEN_ID = "nova-qwen2-5-1-5b-full-sft-20260711"
DOLPHIN_ID = "nova-dolphin3-llama3-1-8b-full-sft-20260712"

MINIMAL_ADAPTER_FILES = (
    "adapter_config.json",
    "adapter_model.safetensors",
    "tokenizer.json",
    "tokenizer_config.json",
    "chat_template.jinja",
    "nova_lora_metadata.json",
    "README.md",
)

PEFT_013_LORA_CONFIG_KEYS = {
    "alpha_pattern",
    "auto_mapping",
    "base_model_name_or_path",
    "bias",
    "fan_in_fan_out",
    "inference_mode",
    "init_lora_weights",
    "layers_pattern",
    "layers_to_transform",
    "loftq_config",
    "lora_alpha",
    "lora_dropout",
    "megatron_config",
    "megatron_core",
    "modules_to_save",
    "peft_type",
    "r",
    "rank_pattern",
    "revision",
    "target_modules",
    "task_type",
    "use_dora",
    "use_rslora",
}

PROMPTS = [
    "What is your name?",
    "My name is Mr Novatron. Remember that.",
    "What is my name?",
    "What is a bird?",
    "Do you like politics?",
    "What do you think is a good thing to learn?",
    "Explain death in a calm natural way.",
    "Teach me something useful about AI in 5 sentences.",
    "If I say I had a hard day, what would you ask me?",
    "Can you make me a simple Temple Run style game?",
    "What should I train you on next?",
    "Tell me the difference between evidence and faith.",
]


RUNNER = r'''
from __future__ import annotations

import gc
import hashlib
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path


WORK = Path("/kaggle/working")
PACKAGE_ZIP = WORK / "nova_raw_adapter_compare_package.zip"
PACKAGE_DIR = WORK / "nova_raw_adapter_compare_package"
RESULT_JSON = WORK / "nova_raw_adapter_compare_result.json"
RESULT_ZIP = WORK / "nova_raw_adapter_compare_result.zip"


def run(cmd):
    print("RUN:", " ".join(map(str, cmd)), flush=True)
    subprocess.check_call(list(map(str, cmd)))


def probe_gpu_without_torch() -> str:
    try:
        return subprocess.check_output(["nvidia-smi", "-L"], text=True, stderr=subprocess.STDOUT).strip()
    except Exception as exc:
        return f"nvidia-smi unavailable: {exc}"


print("NOVA RAW ADAPTER GPU COMPARE START", flush=True)
print("Python:", sys.version, flush=True)
print("Platform:", platform.platform(), flush=True)
gpu_probe = probe_gpu_without_torch()
print("GPU probe:", gpu_probe, flush=True)

if "P100" in gpu_probe and os.environ.get("NOVA_SKIP_TORCH_COMPAT") != "1":
    print("P100 detected; installing a PyTorch CUDA build compatible with sm_60 before importing torch.", flush=True)
    run([sys.executable, "-m", "pip", "install", "-q", "--force-reinstall", "--no-cache-dir",
         "torch==2.5.1", "--index-url", "https://download.pytorch.org/whl/cu121"])

run([sys.executable, "-m", "pip", "install", "-q",
     "transformers==4.45.2", "peft==0.13.2", "accelerate==0.34.2",
     "bitsandbytes==0.43.3", "safetensors>=0.4.5", "requests==2.32.4"])

import requests
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

print("torch:", torch.__version__, flush=True)
print("cuda:", torch.cuda.is_available(), flush=True)
if torch.cuda.is_available():
    print("gpu:", torch.cuda.get_device_name(0), flush=True)
else:
    raise RuntimeError("Kaggle GPU is not enabled. Turn on GPU accelerator before running this cell.")

print("Downloading compare bundle:", BUNDLE_URL, flush=True)
with requests.get(BUNDLE_URL, stream=True, timeout=300) as resp:
    resp.raise_for_status()
    with PACKAGE_ZIP.open("wb") as target:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            if chunk:
                target.write(chunk)
print("Bundle bytes:", PACKAGE_ZIP.stat().st_size, flush=True)

if PACKAGE_DIR.exists():
    shutil.rmtree(PACKAGE_DIR)
PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(PACKAGE_ZIP) as archive:
    archive.extractall(PACKAGE_DIR)

manifest = json.loads((PACKAGE_DIR / "manifest.json").read_text(encoding="utf-8"))
prompts = json.loads((PACKAGE_DIR / "prompts.json").read_text(encoding="utf-8"))
print("Manifest:", json.dumps(manifest, indent=2), flush=True)
print("Prompts:", len(prompts), flush=True)

SYSTEM = """You are Nova Creature.
Speak naturally and directly.
Do not claim to be Qwen, Dolphin, Alibaba, Meta, OpenAI, or a generic AI assistant.
If the user asks your name, say Nova Creature.
For personal facts, only use facts explicitly present in the current prompt."""


def normalize_output(text):
    text = str(text or "").strip()
    for marker in ("NOVA CREATURE RESPONSE:", "ASSISTANT:", "Assistant:", "<|assistant|>"):
        if marker in text:
            text = text.split(marker)[-1].strip()
    return text


def make_prompt(tokenizer, user_text):
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_text},
    ]
    try:
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    except Exception:
        return f"SYSTEM:\n{SYSTEM}\n\nCURRENT USER MESSAGE:\n{user_text}\n\nNOVA CREATURE RESPONSE:\n"


def score_output(prompt, output):
    lower = output.lower()
    score = 50
    notes = []
    bad_markers = ["as an ai", "i am unable", "i cannot assist", "created by alibaba", "qwen", "dolphin", "meta ai"]
    for marker in bad_markers:
        if marker in lower:
            score -= 12
            notes.append("robotic_or_wrong_identity:" + marker)
    if "what is your name" in prompt.lower() and "nova" in lower:
        score += 20
    if "what is a bird" in prompt.lower() and "bird" in lower and ("feather" in lower or "wing" in lower or "vertebrate" in lower):
        score += 18
    if "what is my name" in prompt.lower() and "mr novatron" in lower:
        score += 20
    if 20 <= len(output.split()) <= 120:
        score += 8
    if any(phrase in lower for phrase in ("yeah", "i get", "that makes sense", "here's the thing")):
        score += 4
    if not output:
        score = 0
        notes.append("empty")
    return max(0, min(100, score)), notes


def load_and_run(adapter_info):
    adapter_id = adapter_info["id"]
    adapter_dir = PACKAGE_DIR / "adapters" / adapter_info["folder"]
    config = json.loads((adapter_dir / "adapter_config.json").read_text(encoding="utf-8"))
    base_model = config.get("base_model_name_or_path") or adapter_info.get("base_model")
    print("\\nLOAD", adapter_id, base_model, flush=True)

    quant = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16,
    )
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    base = AutoModelForCausalLM.from_pretrained(
        base_model,
        quantization_config=quant,
        device_map="auto",
        trust_remote_code=True,
        low_cpu_mem_usage=True,
    )
    model = PeftModel.from_pretrained(base, str(adapter_dir))
    model.eval()

    rows = []
    for i, prompt in enumerate(prompts, start=1):
        rendered = make_prompt(tokenizer, prompt)
        encoded = tokenizer(rendered, return_tensors="pt")
        encoded = {k: v.to(model.device) for k, v in encoded.items()}
        start = time.time()
        with torch.no_grad():
            generated = model.generate(
                **encoded,
                max_new_tokens=96,
                do_sample=True,
                temperature=0.45,
                top_p=0.9,
                repetition_penalty=1.08,
                pad_token_id=tokenizer.eos_token_id,
            )
        elapsed = time.time() - start
        new_tokens = generated[0][encoded["input_ids"].shape[-1]:]
        output = normalize_output(tokenizer.decode(new_tokens, skip_special_tokens=True))
        score, notes = score_output(prompt, output)
        row = {
            "index": i,
            "prompt": prompt,
            "raw_output": output,
            "seconds": round(elapsed, 3),
            "score": score,
            "notes": notes,
        }
        rows.append(row)
        print(adapter_id, i, "score", score, "sec", round(elapsed, 2), "=>", output[:160].replace("\\n", " "), flush=True)

    del model, base, tokenizer
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    avg_score = sum(r["score"] for r in rows) / max(1, len(rows))
    avg_seconds = sum(r["seconds"] for r in rows) / max(1, len(rows))
    return {
        "adapter_id": adapter_id,
        "label": adapter_info.get("label", adapter_id),
        "base_model": base_model,
        "train_records": adapter_info.get("train_records"),
        "eval_loss": adapter_info.get("eval_loss"),
        "average_score": round(avg_score, 2),
        "average_seconds": round(avg_seconds, 3),
        "rows": rows,
    }


adapter_results = []
errors = []
for adapter_info in manifest["adapters"]:
    try:
        adapter_results.append(load_and_run(adapter_info))
    except Exception as exc:
        print("ADAPTER_ERROR", adapter_info.get("id"), repr(exc), flush=True)
        errors.append({"adapter_id": adapter_info.get("id"), "error": repr(exc)})
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

winner = None
if adapter_results:
    winner = sorted(adapter_results, key=lambda r: (r["average_score"], -r["average_seconds"]), reverse=True)[0]["adapter_id"]

report = {
    "ok": bool(adapter_results),
    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "",
    "torch": torch.__version__,
    "prompt_count": len(prompts),
    "winner": winner,
    "adapters": adapter_results,
    "errors": errors,
    "manifest": manifest,
}
RESULT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\\n", encoding="utf-8")
with zipfile.ZipFile(RESULT_ZIP, "w", zipfile.ZIP_DEFLATED) as archive:
    archive.write(RESULT_JSON, RESULT_JSON.name)

print("RESULT_JSON", RESULT_JSON, RESULT_JSON.stat().st_size, flush=True)
print("RESULT_ZIP", RESULT_ZIP, RESULT_ZIP.stat().st_size, flush=True)

if TRANSFER_BASE and TRANSFER_TOKEN:
    upload_url = f"{TRANSFER_BASE}/upload?token={TRANSFER_TOKEN}&name={RESULT_ZIP.name}"
    print("Uploading result:", upload_url, flush=True)
    with RESULT_ZIP.open("rb") as source:
        upload_resp = requests.post(upload_url, data=source, timeout=300)
    print("UPLOAD_STATUS", upload_resp.status_code, upload_resp.text[:800], flush=True)
    upload_resp.raise_for_status()

print("NOVA RAW ADAPTER GPU COMPARE DONE", flush=True)
'''


def _copy_minimal_adapter(source: Path, target: Path) -> int:
    target.mkdir(parents=True, exist_ok=True)
    total = 0
    for name in MINIMAL_ADAPTER_FILES:
        src = source / name
        if not src.exists():
            continue
        dst = target / name
        if name == "adapter_config.json":
            raw_config = _load_json(src)
            clean_config = {
                key: value
                for key, value in raw_config.items()
                if key in PEFT_013_LORA_CONFIG_KEYS
            }
            dst.write_text(json.dumps(clean_config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        else:
            shutil.copy2(src, dst)
        total += dst.stat().st_size
    return total


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def prepare(timestamp: str, transfer_base: str = "", transfer_token: str = "") -> dict:
    work_dir = DEFAULT_OUT / f"nova_raw_adapter_compare_{timestamp}"
    package_dir = work_dir / "package"
    adapters_dir = package_dir / "adapters"
    qwen_source = ADAPTER_ROOT / QWEN_ID
    dolphin_source = ADAPTER_ROOT / DOLPHIN_ID
    if work_dir.exists():
        shutil.rmtree(work_dir)
    adapters_dir.mkdir(parents=True, exist_ok=True)

    qwen_bytes = _copy_minimal_adapter(qwen_source, adapters_dir / "qwen")
    dolphin_bytes = _copy_minimal_adapter(dolphin_source, adapters_dir / "dolphin")
    qwen_meta = _load_json(qwen_source / "nova_lora_metadata.json")
    dolphin_meta = _load_json(dolphin_source / "nova_lora_metadata.json")

    manifest = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "purpose": "raw_gpu_adapter_compare",
        "adapters": [
            {
                "id": QWEN_ID,
                "folder": "qwen",
                "label": "RAW Qwen adapter",
                "base_model": "Qwen/Qwen2.5-1.5B-Instruct",
                "train_records": qwen_meta.get("train_records"),
                "eval_loss": (qwen_meta.get("eval_metrics") or {}).get("eval_loss"),
                "bytes": qwen_bytes,
            },
            {
                "id": DOLPHIN_ID,
                "folder": "dolphin",
                "label": "RAW Dolphin adapter",
                "base_model": "dphn/Dolphin3.0-Llama3.1-8B",
                "train_records": dolphin_meta.get("train_records"),
                "eval_loss": (dolphin_meta.get("eval_metrics") or {}).get("eval_loss"),
                "bytes": dolphin_bytes,
            },
        ],
    }
    (package_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (package_dir / "prompts.json").write_text(json.dumps(PROMPTS, indent=2) + "\n", encoding="utf-8")
    (package_dir / "run_raw_adapter_compare_gpu.py").write_text(RUNNER, encoding="utf-8")

    zip_path = work_dir / "nova_raw_adapter_compare_package.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in package_dir.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(package_dir))

    cell = textwrap.dedent(
        f"""
        # Nova raw adapter GPU compare — generated {timestamp}
        BUNDLE_URL = "{transfer_base.rstrip('/')}/bundle" if "{transfer_base}" else "PASTE_TRANSFER_BUNDLE_URL_HERE"
        TRANSFER_BASE = "{transfer_base.rstrip('/')}"
        TRANSFER_TOKEN = "{transfer_token}"

        import urllib.request, pathlib, zipfile, runpy
        cell_zip = pathlib.Path("/kaggle/working/nova_raw_adapter_compare_package.zip")
        cell_dir = pathlib.Path("/kaggle/working/nova_raw_adapter_compare_package")
        print("Downloading:", BUNDLE_URL)
        urllib.request.urlretrieve(BUNDLE_URL, cell_zip)
        if cell_dir.exists():
            import shutil; shutil.rmtree(cell_dir)
        cell_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(cell_zip) as archive:
            archive.extractall(cell_dir)
        runpy.run_path(str(cell_dir / "run_raw_adapter_compare_gpu.py"), init_globals={{
            "BUNDLE_URL": BUNDLE_URL,
            "TRANSFER_BASE": TRANSFER_BASE,
            "TRANSFER_TOKEN": TRANSFER_TOKEN,
        }})
        """
    ).strip() + "\n"
    cell_path = work_dir / "nova_raw_adapter_compare_kaggle_cell.py"
    cell_path.write_text(cell, encoding="utf-8")

    return {
        "work_dir": str(work_dir),
        "package_dir": str(package_dir),
        "zip_path": str(zip_path),
        "zip_bytes": zip_path.stat().st_size,
        "cell_path": str(cell_path),
        "manifest": manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare Nova raw adapter GPU comparison Kaggle package.")
    parser.add_argument("--timestamp", default=time.strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--transfer-base", default="")
    parser.add_argument("--transfer-token", default="")
    args = parser.parse_args()
    result = prepare(args.timestamp, args.transfer_base, args.transfer_token)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
