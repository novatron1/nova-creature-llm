import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_tailscale import NovaTailscaleManager, TailscaleError  # noqa: E402


class FakeRunner:
    def __init__(self, *, conflict: bool = False, funnel: bool = False):
        self.calls: list[list[str]] = []
        self.enabled = False
        self.conflict = conflict
        self.funnel = funnel

    def __call__(
        self, arguments: list[str], timeout: float
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(arguments))
        if arguments[1:] == ["status", "--json"]:
            payload = {
                "BackendState": "Running",
                "Self": {
                    "Online": True,
                    "DNSName": "nova-host.example.ts.net.",
                },
                "User": {"1": {"LoginName": "owner@example.test"}},
            }
        elif arguments[1:] == ["serve", "status", "--json"]:
            handlers = {}
            if self.enabled or self.conflict or self.funnel:
                handlers = {
                    "nova-host.example.ts.net:8443": {
                        "Handlers": {
                            "/": {
                                "Proxy": (
                                    "http://127.0.0.1:9090"
                                    if self.conflict
                                    else "http://127.0.0.1:3000"
                                )
                            }
                        }
                    }
                }
            payload = {
                "Web": handlers,
                "AllowFunnel": (
                    {"nova-host.example.ts.net:8443": True}
                    if self.funnel
                    else {}
                ),
            }
        elif arguments[1:] == [
            "serve",
            "--bg",
            "--yes",
            "--https=8443",
            "http://127.0.0.1:3000",
        ]:
            self.enabled = True
            payload = {}
        elif arguments[1:] == ["serve", "--https=8443", "off"]:
            self.enabled = False
            payload = {}
        else:
            return subprocess.CompletedProcess(
                arguments, 1, "", "unexpected command"
            )
        return subprocess.CompletedProcess(arguments, 0, json.dumps(payload), "")


@pytest.fixture
def fake_runner() -> FakeRunner:
    return FakeRunner()


def _manager(runner: FakeRunner) -> NovaTailscaleManager:
    return NovaTailscaleManager(
        nova_port=3000,
        https_port=8443,
        executable="tailscale",
        command_runner=runner,
    )


def test_status_reports_private_url_without_leaking_account(fake_runner):
    status = _manager(fake_runner).status()

    assert status["connected"] is True
    assert status["private_url"] == "https://nova-host.example.ts.net:8443"
    assert status["serve_enabled"] is False
    assert status["serve_conflict"] is False
    assert status["reason"] == "serve_not_configured"
    assert "owner@example.test" not in json.dumps(status)
    assert "User" not in status


def test_enable_uses_private_8443_and_confirms_postcondition(fake_runner):
    enabled = _manager(fake_runner).enable()

    assert enabled["serve_enabled"] is True
    assert enabled["reason"] == "ready"
    assert [
        "tailscale",
        "serve",
        "--bg",
        "--yes",
        "--https=8443",
        "http://127.0.0.1:3000",
    ] in fake_runner.calls


def test_enable_refuses_to_replace_an_existing_8443_handler():
    runner = FakeRunner(conflict=True)

    with pytest.raises(TailscaleError, match="8443"):
        _manager(runner).enable()

    assert not any(call[1:3] == ["serve", "--bg"] for call in runner.calls)


def test_enable_refuses_a_public_funnel_on_8443():
    runner = FakeRunner(funnel=True)

    status = _manager(runner).status()
    assert status["serve_conflict"] is True
    assert status["reason"] == "https_port_public"
    with pytest.raises(TailscaleError, match="public Funnel"):
        _manager(runner).enable()


def test_disable_removes_only_the_owned_mapping(fake_runner):
    manager = _manager(fake_runner)
    manager.enable()

    disabled = manager.disable()

    assert disabled["serve_enabled"] is False
    assert ["tailscale", "serve", "--https=8443", "off"] in fake_runner.calls


def test_disable_refuses_an_unowned_mapping():
    runner = FakeRunner(conflict=True)

    with pytest.raises(TailscaleError, match="does not own"):
        _manager(runner).disable()


def test_set_nova_port_updates_the_expected_owned_target(fake_runner):
    manager = _manager(fake_runner)

    manager.set_nova_port(8765)

    assert manager.nova_port == 8765
    with pytest.raises(ValueError, match="between 1 and 65535"):
        manager.set_nova_port(0)
