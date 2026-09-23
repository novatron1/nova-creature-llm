"""Private localhost Kokoro worker for Nova's local neural GPU voice."""

from __future__ import annotations

import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nova_kokoro_voice import synthesize_to_wav


_PIPELINE = None
_PIPELINE_LOCK = threading.RLock()


def get_pipeline():
    global _PIPELINE
    if _PIPELINE is not None:
        return _PIPELINE
    with _PIPELINE_LOCK:
        if _PIPELINE is not None:
            return _PIPELINE
        import torch
        from kokoro import KPipeline

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable for Nova's neural voice")
        _PIPELINE = KPipeline(
            lang_code="a",
            repo_id="hexgrad/Kokoro-82M",
            device="cuda",
        )
        return _PIPELINE


class VoiceHandler(BaseHTTPRequestHandler):
    server_version = "NovaKokoroVoice/1.0"

    def log_message(self, format, *args):
        return

    def _send_json(self, status, payload):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/health":
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        try:
            import torch

            self._send_json(
                200,
                {
                    "ok": bool(torch.cuda.is_available()),
                    "device": "cuda" if torch.cuda.is_available() else "unavailable",
                    "model_loaded": _PIPELINE is not None,
                },
            )
        except Exception as exc:
            self._send_json(503, {"ok": False, "error": str(exc)})

    def do_POST(self):
        if self.path != "/synthesize":
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0 or length > 1_000_000:
                raise ValueError("invalid request size")
            request = json.loads(self.rfile.read(length).decode("utf-8"))
            text = str(request.get("text") or "").strip()
            voice = str(request.get("voice") or "af_heart").strip() or "af_heart"
            speed = max(0.5, min(float(request.get("speed") or 1.0), 2.0))
            with _PIPELINE_LOCK:
                payload = synthesize_to_wav(
                    text,
                    voice=voice,
                    pipeline_factory=get_pipeline,
                    device="cuda",
                    speed=speed,
                )
            self._send_json(200, payload)
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            self._send_json(503, {"ok": False, "error": str(exc)})


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8890)
    args = parser.parse_args(argv)
    get_pipeline()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), VoiceHandler)
    print(f"Nova Kokoro GPU voice ready on http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
