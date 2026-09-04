from __future__ import annotations

from http.server import HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
import sys
from threading import Thread
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import nova_enhanced_server as server  # noqa: E402


class ThreadedTestServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def start_server():
    httpd = ThreadedTestServer(("127.0.0.1", 0), server.NovaHandler)
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, f"http://127.0.0.1:{httpd.server_port}"


def get_text(base_url, path):
    with urllib.request.urlopen(base_url + path, timeout=10) as response:
        headers = response.headers
        assert response.status == 200
        assert headers.get_content_type() == "text/html"
        assert headers["Cache-Control"] == "no-cache"
        assert headers["X-Content-Type-Options"] == "nosniff"
        return response.read().decode("utf-8"), headers["Content-Security-Policy"]


def get_status(base_url, path):
    try:
        with urllib.request.urlopen(base_url + path, timeout=10) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def test_companion_config_defaults_to_enabled_but_not_default(monkeypatch):
    monkeypatch.delenv("NOVA_COMPANION_ENABLED", raising=False)
    monkeypatch.delenv("NOVA_COMPANION_DEFAULT", raising=False)
    monkeypatch.setattr(server, "_runtime_config_values", lambda: {})

    assert server._companion_ui_config() == {"enabled": True, "default": False}


def test_companion_classic_and_default_routes(monkeypatch):
    monkeypatch.setattr(
        server,
        "_companion_ui_config",
        lambda: {"enabled": True, "default": False},
    )
    httpd, base_url = start_server()
    try:
        classic, classic_csp = get_text(base_url, "/classic")
        companion, companion_csp = get_text(base_url, "/companion")
        root, _root_csp = get_text(base_url, "/")

        assert classic == server.WEB_HTML
        assert companion == server.COMPANION_WEB_HTML
        assert root == server.WEB_HTML
        assert "script-src 'self' 'unsafe-inline'" in classic_csp
        assert "style-src 'self' 'unsafe-inline'" in classic_csp
        assert "script-src 'self'" in companion_csp
        assert "style-src 'self'" in companion_csp
        assert "unsafe-inline" not in companion_csp

        monkeypatch.setattr(
            server,
            "_companion_ui_config",
            lambda: {"enabled": True, "default": True},
        )
        default, default_csp = get_text(base_url, "/")
        assert default == server.COMPANION_WEB_HTML
        assert "unsafe-inline" not in default_csp
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_disabled_companion_route_is_not_found(monkeypatch):
    monkeypatch.setattr(
        server,
        "_companion_ui_config",
        lambda: {"enabled": False, "default": False},
    )
    httpd, base_url = start_server()
    try:
        assert get_status(base_url, "/companion") == 404
        assert get_status(base_url, "/classic") == 200
    finally:
        httpd.shutdown()
        httpd.server_close()
