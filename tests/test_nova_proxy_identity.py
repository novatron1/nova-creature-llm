from email.message import Message
from pathlib import Path
from types import SimpleNamespace
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_proxy_identity import trusted_tailscale_client_key  # noqa: E402


def _handler(peer: str, login: str = "phone@example.test") -> SimpleNamespace:
    headers = Message()
    headers["Tailscale-User-Login"] = login
    return SimpleNamespace(client_address=(peer, 41000), headers=headers)


def test_trusted_tailscale_identity_requires_explicit_policy_and_loopback():
    assert trusted_tailscale_client_key(_handler("127.0.0.1"), enabled=False) is None
    assert trusted_tailscale_client_key(_handler("192.0.2.44"), enabled=True) is None


def test_trusted_tailscale_identity_is_opaque_and_stable():
    first = trusted_tailscale_client_key(_handler("127.0.0.1"), enabled=True)
    second = trusted_tailscale_client_key(_handler("::1"), enabled=True)

    assert first == second
    assert first is not None and first.startswith("tailscale:")
    assert "phone@example.test" not in first
    assert len(first) == len("tailscale:") + 24


def test_trusted_tailscale_identity_rejects_control_characters():
    assert (
        trusted_tailscale_client_key(
            _handler("127.0.0.1", "phone@example.test\nspoofed"), enabled=True
        )
        is None
    )


def test_trusted_tailscale_identity_can_read_the_environment_policy():
    assert (
        trusted_tailscale_client_key(
            _handler("127.0.0.1"),
            env={"NOVA_TRUST_TAILSCALE_SERVE": "true"},
        )
        is not None
    )
