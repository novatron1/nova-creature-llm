"""Install Nova's trained Dolphin LoRA on top of an existing Ollama model.

This uses Ollama's local blob and create APIs. It does not download a base model,
merge full weights, add Nova instructions, or contact Hugging Face.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ADAPTER_ID = "nova-dolphin3-llama3-1-8b-full-sft-20260712"
DEFAULT_ADAPTER_DIR = ROOT / "models" / "lora_adapters" / DEFAULT_ADAPTER_ID
DEFAULT_BASE_MODEL = "dolphin3:latest"
DEFAULT_MODEL_NAME = "nova-dolphin3-lora"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _adapter_files(adapter_dir: str | Path) -> dict[str, Path]:
    directory = Path(adapter_dir).resolve()
    config = directory / "adapter_config.json"
    weights = directory / "adapter_model.safetensors"
    if not weights.exists():
        weights = directory / "adapter_model.bin"
    missing = [str(path.name) for path in (config, weights) if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing trained Dolphin adapter file(s): " + ", ".join(missing))
    return {"adapter_config.json": config, weights.name: weights}


def build_install_plan(
    *,
    adapter_dir: str | Path = DEFAULT_ADAPTER_DIR,
    base_model: str = DEFAULT_BASE_MODEL,
    model_name: str = DEFAULT_MODEL_NAME,
    ollama_url: str = DEFAULT_OLLAMA_URL,
) -> dict[str, Any]:
    """Describe a no-download install and calculate its content hashes."""
    files = _adapter_files(adapter_dir)
    return {
        "adapter_dir": str(Path(adapter_dir).resolve()),
        "base_model": str(base_model),
        "model_name": str(model_name),
        "ollama_url": str(ollama_url).rstrip("/"),
        "downloads_required": False,
        "nova_system_prompt_added": False,
        "files": {
            name: {"path": str(path), "size": path.stat().st_size, "digest": _sha256(path)}
            for name, path in files.items()
        },
    }


def build_create_payload(plan: dict[str, Any]) -> dict[str, Any]:
    """Build the Ollama create request without provider-specific data leaking into Nova."""
    return {
        "model": plan["model_name"],
        "from": plan["base_model"],
        "adapters": {name: item["digest"] for name, item in plan["files"].items()},
        "parameters": {"temperature": 0.55, "top_p": 0.9, "num_ctx": 8192},
        "stream": False,
    }


def _api_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def _request_json(base_url: str, method: str, path: str, payload: dict[str, Any] | None = None, timeout: int = 600) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        _api_url(base_url, path),
        data=body,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"Ollama request {method} {path} failed: HTTP {exc.code} {detail}"
        ) from exc
    if not data:
        return {}
    result = json.loads(data.decode("utf-8"))
    return result if isinstance(result, dict) else {}


def _blob_exists(base_url: str, digest: str, timeout: int = 10) -> bool:
    request = urllib.request.Request(_api_url(base_url, "/api/blobs/" + digest), method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= int(response.status) < 300
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def _upload_blob(base_url: str, digest: str, path: Path, timeout: int = 600) -> None:
    """Stream a potentially large adapter file without reading it all into RAM."""
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Ollama URL must be an HTTP(S) URL")
    connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    connection = connection_type(parsed.hostname, port, timeout=timeout)
    prefix = parsed.path.rstrip("/")
    endpoint = prefix + "/api/blobs/" + digest
    try:
        connection.putrequest("POST", endpoint)
        connection.putheader("Content-Type", "application/octet-stream")
        connection.putheader("Content-Length", str(path.stat().st_size))
        connection.endheaders()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                connection.send(chunk)
        response = connection.getresponse()
        response.read()
        if not 200 <= response.status < 300:
            raise RuntimeError(f"Ollama rejected {path.name}: HTTP {response.status} {response.reason}")
    finally:
        connection.close()


def install_adapter(plan: dict[str, Any], *, timeout: int = 600) -> dict[str, Any]:
    """Install the planned adapter using only the configured Ollama server."""
    base_url = str(plan["ollama_url"])
    models = _request_json(base_url, "GET", "/api/tags", timeout=min(timeout, 30)).get("models", [])
    available = {
        str(item.get("name") or item.get("model") or "").removesuffix(":latest")
        for item in models
        if isinstance(item, dict)
    }
    requested_base = str(plan["base_model"]).removesuffix(":latest")
    if requested_base not in available:
        raise RuntimeError(
            f"Required local Ollama base model {plan['base_model']!r} is not installed. "
            "No download was attempted."
        )

    uploaded: list[str] = []
    reused: list[str] = []
    for item in plan["files"].values():
        digest = str(item["digest"])
        if _blob_exists(base_url, digest):
            reused.append(digest)
            continue
        _upload_blob(base_url, digest, Path(item["path"]), timeout=timeout)
        uploaded.append(digest)

    result = _request_json(base_url, "POST", "/api/create", build_create_payload(plan), timeout=timeout)
    if str(result.get("status") or "").lower() not in {"success", "complete"}:
        raise RuntimeError("Ollama did not confirm adapter creation: " + json.dumps(result, sort_keys=True))
    return {**plan, "ok": True, "status": result.get("status"), "uploaded": uploaded, "reused": reused}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install Nova's trained Dolphin LoRA into an existing local Ollama Dolphin model.")
    parser.add_argument("--adapter-dir", default=str(DEFAULT_ADAPTER_DIR))
    parser.add_argument("--base-model", default=os.environ.get("NOVA_DOLPHIN_LORA_BASE_MODEL", DEFAULT_BASE_MODEL))
    parser.add_argument("--model-name", default=os.environ.get("NOVA_DOLPHIN_LORA_OLLAMA_MODEL", DEFAULT_MODEL_NAME))
    parser.add_argument("--ollama-url", default=os.environ.get("NOVA_OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL))
    parser.add_argument("--install", action="store_true", help="Perform the local install. Without this flag, only print the plan.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    plan = build_install_plan(
        adapter_dir=args.adapter_dir,
        base_model=args.base_model,
        model_name=args.model_name,
        ollama_url=args.ollama_url,
    )
    result = install_adapter(plan) if args.install else {**plan, "ok": True, "dry_run": True}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
