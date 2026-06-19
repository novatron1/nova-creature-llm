from __future__ import annotations

import json
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    from v052_role_brain_router import run as router_run
except Exception as e:
    router_run = None
    ROUTER_IMPORT_ERROR = repr(e)
else:
    ROUTER_IMPORT_ERROR = None

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ["/api/chat", "/api/router-chat"]:
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length", "0") or "0")
        data = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        prompt = str(data.get("prompt") or data.get("message") or "").strip()
        if not prompt:
            self.send_json({"ok": False, "error": "No prompt received."})
            return
        if router_run is None:
            self.send_json({"ok": False, "error": "Router import failed", "detail": ROUTER_IMPORT_ERROR})
            return

        report = router_run(prompt)
        answers = [r["final_answer"] for r in report["results"]]
        routes = [r["selected_route"] for r in report["results"]]
        final = "\n".join(f"{i+1}. {a}" for i, a in enumerate(answers)) if len(answers) > 1 else (answers[0] if answers else "I do not know.")
        self.send_json({"ok": True, "source_mode": "Role-Brain Router v052 Cloud", "answer": final, "routes": routes, "report": report})

    def send_json(self, obj):
        raw = json.dumps(obj, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

def main():
    port = 8766
    print("Nova Creature Cloud Chat Adapter")
    print("Project root:", ROOT)
    print(f"Serving http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()

if __name__ == "__main__":
    main()
