from __future__ import annotations

import argparse
import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = ROOT / "sandbox" / "gpu_training_exports" / "nova_kaggle_gpu_training.zip"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "kaggle_imports"


def _safe_filename(name: str) -> str:
    cleaned = "".join(ch for ch in name if ch.isalnum() or ch in ("-", "_", ".", " ")).strip()
    return cleaned or "kaggle_upload.bin"


class TransferHandler(BaseHTTPRequestHandler):
    server_version = "NovaKaggleTransfer/1.0"

    def _send_json(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(200, {"ok": True, "service": "nova_kaggle_transfer"})
            return

        if parsed.path in {"/bundle", "/bundle/nova_kaggle_gpu_training.zip"}:
            bundle_path: Path = self.server.bundle_path  # type: ignore[attr-defined]
            if not bundle_path.exists():
                self._send_json(404, {"ok": False, "error": "bundle_not_found", "path": str(bundle_path)})
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="{bundle_path.name}"')
            self.send_header("Content-Length", str(bundle_path.stat().st_size))
            self.end_headers()
            with bundle_path.open("rb") as source:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            return

        self._send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/upload_chunk":
            self._handle_upload_chunk(parsed)
            return

        if parsed.path != "/upload":
            self._send_json(404, {"ok": False, "error": "not_found"})
            return

        query = parse_qs(parsed.query)
        token = query.get("token", [""])[0]
        expected_token: str = self.server.upload_token  # type: ignore[attr-defined]
        if not expected_token or token != expected_token:
            self._send_json(403, {"ok": False, "error": "bad_token"})
            return

        length_text = self.headers.get("Content-Length")
        if not length_text:
            self._send_json(411, {"ok": False, "error": "missing_content_length"})
            return
        try:
            remaining = int(length_text)
        except ValueError:
            self._send_json(400, {"ok": False, "error": "bad_content_length"})
            return

        output_dir: Path = self.server.output_dir  # type: ignore[attr-defined]
        output_dir.mkdir(parents=True, exist_ok=True)
        requested_name = query.get("name", ["nova_lora_sft_result.zip"])[0]
        filename = _safe_filename(requested_name)
        final_path = output_dir / filename
        part_path = final_path.with_suffix(final_path.suffix + ".part")

        digest = hashlib.sha256()
        total = 0
        with part_path.open("wb") as target:
            while remaining > 0:
                chunk = self.rfile.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                target.write(chunk)
                digest.update(chunk)
                total += len(chunk)
                remaining -= len(chunk)

        if remaining != 0:
            try:
                part_path.unlink()
            except FileNotFoundError:
                pass
            self._send_json(400, {"ok": False, "error": "incomplete_upload", "bytes_received": total})
            return

        part_path.replace(final_path)
        sha256 = digest.hexdigest()
        metadata = {
            "ok": True,
            "filename": filename,
            "path": str(final_path),
            "bytes": total,
            "sha256": sha256,
        }
        (final_path.with_suffix(final_path.suffix + ".sha256")).write_text(sha256 + "\n", encoding="utf-8")
        (output_dir / "latest_upload.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self._send_json(200, metadata)

    def _handle_upload_chunk(self, parsed) -> None:
        query = parse_qs(parsed.query)
        token = query.get("token", [""])[0]
        expected_token: str = self.server.upload_token  # type: ignore[attr-defined]
        if not expected_token or token != expected_token:
            self._send_json(403, {"ok": False, "error": "bad_token"})
            return

        length_text = self.headers.get("Content-Length")
        if not length_text:
            self._send_json(411, {"ok": False, "error": "missing_content_length"})
            return
        try:
            remaining = int(length_text)
            index = int(query.get("index", [""])[0])
            total_chunks = int(query.get("total", [""])[0])
            total_size_text = query.get("total_size", [""])[0]
            expected_size = int(total_size_text) if total_size_text else None
        except ValueError:
            self._send_json(400, {"ok": False, "error": "bad_chunk_metadata"})
            return

        if index < 0 or total_chunks <= 0 or index >= total_chunks:
            self._send_json(400, {"ok": False, "error": "chunk_index_out_of_range"})
            return

        output_dir: Path = self.server.output_dir  # type: ignore[attr-defined]
        output_dir.mkdir(parents=True, exist_ok=True)
        requested_name = query.get("name", ["nova_lora_sft_result.zip"])[0]
        filename = _safe_filename(requested_name)
        final_path = output_dir / filename
        chunks_dir = output_dir / f".{filename}.chunks"
        chunks_dir.mkdir(parents=True, exist_ok=True)
        chunk_path = chunks_dir / f"{index:06d}.chunk"
        part_path = chunk_path.with_suffix(".chunk.part")

        total = 0
        with part_path.open("wb") as target:
            while remaining > 0:
                chunk = self.rfile.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                target.write(chunk)
                total += len(chunk)
                remaining -= len(chunk)

        if remaining != 0:
            try:
                part_path.unlink()
            except FileNotFoundError:
                pass
            self._send_json(400, {"ok": False, "error": "incomplete_chunk", "bytes_received": total, "index": index})
            return

        part_path.replace(chunk_path)
        present = sorted(chunks_dir.glob("*.chunk"))
        if len(present) != total_chunks:
            self._send_json(
                200,
                {
                    "ok": True,
                    "status": "chunk_saved",
                    "filename": filename,
                    "index": index,
                    "received_chunks": len(present),
                    "total_chunks": total_chunks,
                    "bytes": total,
                },
            )
            return

        expected_paths = [chunks_dir / f"{i:06d}.chunk" for i in range(total_chunks)]
        if not all(path.exists() for path in expected_paths):
            self._send_json(409, {"ok": False, "error": "chunk_gap", "received_chunks": len(present), "total_chunks": total_chunks})
            return

        digest = hashlib.sha256()
        assembled = 0
        assembled_part = final_path.with_suffix(final_path.suffix + ".part")
        with assembled_part.open("wb") as target:
            for path in expected_paths:
                with path.open("rb") as source:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        target.write(chunk)
                        digest.update(chunk)
                        assembled += len(chunk)

        if expected_size is not None and assembled != expected_size:
            try:
                assembled_part.unlink()
            except FileNotFoundError:
                pass
            self._send_json(400, {"ok": False, "error": "assembled_size_mismatch", "bytes": assembled, "expected_bytes": expected_size})
            return

        sha256 = digest.hexdigest()
        expected_sha256 = query.get("sha256", [""])[0].strip().lower()
        if expected_sha256 and sha256.lower() != expected_sha256:
            try:
                assembled_part.unlink()
            except FileNotFoundError:
                pass
            self._send_json(400, {"ok": False, "error": "sha256_mismatch", "sha256": sha256, "expected_sha256": expected_sha256})
            return

        assembled_part.replace(final_path)
        metadata = {
            "ok": True,
            "status": "assembled",
            "filename": filename,
            "path": str(final_path),
            "bytes": assembled,
            "sha256": sha256,
            "chunks": total_chunks,
        }
        (final_path.with_suffix(final_path.suffix + ".sha256")).write_text(sha256 + "\n", encoding="utf-8")
        (output_dir / "latest_upload.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        for path in expected_paths:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        try:
            chunks_dir.rmdir()
        except OSError:
            pass
        self._send_json(200, metadata)

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.address_string()} - {fmt % args}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Temporary transfer bridge for Nova Kaggle training artifacts.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=58776)
    parser.add_argument("--token", required=True)
    parser.add_argument("--bundle-path", default=str(DEFAULT_BUNDLE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), TransferHandler)
    server.upload_token = args.token  # type: ignore[attr-defined]
    server.bundle_path = Path(args.bundle_path).resolve()  # type: ignore[attr-defined]
    server.output_dir = Path(args.output_dir).resolve()  # type: ignore[attr-defined]
    print(
        json.dumps(
            {
                "ok": True,
                "listening": f"http://{args.host}:{args.port}",
                "bundle_path": str(server.bundle_path),
                "output_dir": str(server.output_dir),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
