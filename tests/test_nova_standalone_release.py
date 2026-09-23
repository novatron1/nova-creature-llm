from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_standalone_release_script_has_safe_allowlist_launcher_and_rollback_manifest():
    script = (ROOT / "tools" / "build_nova_windows_release.ps1").read_text(encoding="utf-8")
    for marker in [
        "Nova_Start.bat",
        "NOVA_RELEASE_MANIFEST.json",
        "rollback.json",
        "checkpoints",
        "model_weights",
        "NOVA_GPU_HUB_INSTALL.bat",
        "nova_doctor.py",
    ]:
        assert marker in script
    assert 'py "%~dp0nova_enhanced_server.py" 3000' in script


def test_standalone_docs_describe_portable_bundle_and_no_model_weights():
    docs = (ROOT / "docs" / "NOVA_STANDALONE_INSTALL.md").read_text(encoding="utf-8")
    assert "standalone" in docs.lower()
    assert "model weights" in docs.lower()
    assert "rollback" in docs.lower()
