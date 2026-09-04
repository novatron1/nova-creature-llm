from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from nova_anywhere import run_anywhere, wait_for_nova  # noqa: E402
from nova_tailscale import TailscaleError  # noqa: E402


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Process:
    def __init__(self, *, exit_code=0):
        self.exit_code = exit_code
        self.terminated = False
        self.killed = False

    def poll(self):
        return None

    def wait(self, timeout=None):
        return self.exit_code

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


class _Manager:
    instances = []

    def __init__(self, nova_port, https_port):
        self.nova_port = nova_port
        self.https_port = https_port
        self.enable_calls = 0
        type(self).instances.append(self)

    def enable(self):
        self.enable_calls += 1
        return {
            "ok": True,
            "serve_enabled": True,
            "serve_conflict": False,
            "private_url": "https://nova-host.example.ts.net:8443",
            "reason": "ready",
        }


class _FailingManager(_Manager):
    def enable(self):
        raise TailscaleError("Tailscale could not update the private connection.")


def _application_root(tmp_path):
    (tmp_path / "nova_enhanced_server.py").write_text("# server\n", encoding="utf-8")
    return tmp_path


def test_run_anywhere_enables_private_serve_and_starts_loopback_nova(tmp_path):
    root = _application_root(tmp_path)
    opened_urls = []
    process = _Process()

    def fake_popen(arguments, *, cwd, env):
        fake_popen.arguments = arguments
        fake_popen.cwd = cwd
        fake_popen.environment = env
        return process

    result = run_anywhere(
        root,
        3000,
        8443,
        manager_factory=_Manager,
        popen_factory=fake_popen,
        browser_open=opened_urls.append,
        health_opener=lambda *_args, **_kwargs: _Response(),
        sleeper=lambda _seconds: None,
    )

    assert result == 0
    assert fake_popen.arguments == [sys.executable, "nova_enhanced_server.py", "3000"]
    assert fake_popen.cwd == str(root.resolve())
    assert fake_popen.environment["NOVA_TRUST_TAILSCALE_SERVE"] == "true"
    assert fake_popen.environment["NOVA_HOST"] == "127.0.0.1"
    assert fake_popen.environment["NOVA_TAILSCALE_HTTPS_PORT"] == "8443"
    assert opened_urls == ["http://127.0.0.1:3000/classic?panel=settings"]


def test_run_anywhere_does_not_start_nova_when_tailscale_enable_fails(tmp_path):
    root = _application_root(tmp_path)
    calls = []

    with pytest.raises(TailscaleError, match="private connection"):
        run_anywhere(
            root,
            3000,
            8443,
            manager_factory=_FailingManager,
            popen_factory=lambda *args, **kwargs: calls.append((args, kwargs)),
        )

    assert calls == []


def test_wait_for_nova_stops_when_child_exits():
    class ExitedProcess(_Process):
        def poll(self):
            return 7

    assert wait_for_nova(
        "http://127.0.0.1:3000/healthz",
        ExitedProcess(),
        timeout_seconds=0.01,
        opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")),
        sleeper=lambda _seconds: None,
    ) is False


def test_run_anywhere_terminates_only_its_child_when_health_never_arrives(tmp_path):
    root = _application_root(tmp_path)
    process = _Process(exit_code=0)

    result = run_anywhere(
        root,
        3000,
        8443,
        manager_factory=_Manager,
        popen_factory=lambda *_args, **_kwargs: process,
        browser_open=lambda _url: None,
        health_opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")),
        sleeper=lambda _seconds: None,
        health_timeout_seconds=0.01,
    )

    assert result != 0
    assert process.terminated is True
    assert process.killed is False
