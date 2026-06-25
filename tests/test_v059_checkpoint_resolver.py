from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_checkpoint_registry import CheckpointRegistry, sha256
import v059_checkpoint_resolver as resolver


def test_resolver_returns_structured_error_for_missing_registered_checkpoint(tmp_path, monkeypatch):
    checkpoint = tmp_path / "left.pt"
    checkpoint.write_bytes(b"baseline")
    registry = CheckpointRegistry(tmp_path)
    registry.register_baseline("left_hemisphere", checkpoint, sha256(checkpoint))
    checkpoint.unlink()
    monkeypatch.setattr(resolver, "root", lambda: tmp_path)

    result = resolver.resolve_checkpoint("left_hemisphere")

    assert result["exists"] is False
    assert result["promote_ready"] is False
    assert "missing" in result["error"].lower()


def test_resolver_returns_structured_error_for_registered_hash_mismatch(tmp_path, monkeypatch):
    checkpoint = tmp_path / "left.pt"
    checkpoint.write_bytes(b"baseline")
    registry = CheckpointRegistry(tmp_path)
    registry.register_baseline("left_hemisphere", checkpoint, sha256(checkpoint))
    checkpoint.write_bytes(b"tampered")
    monkeypatch.setattr(resolver, "root", lambda: tmp_path)

    result = resolver.resolve_checkpoint("left_hemisphere")

    assert result["exists"] is False
    assert result["promote_ready"] is False
    assert "hash mismatch" in result["error"].lower()
