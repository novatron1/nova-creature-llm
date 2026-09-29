"""Studio configuration is opt-in and starts no model at app startup."""
from pathlib import Path
import subprocess

from nova_gateway.config import GatewayConfig
from nova_gateway.core import NovaGatewayCore


def test_studio_configuration_resolves_paths_and_no_models_start(tmp_path, monkeypatch):
    config = GatewayConfig.from_env({'NOVA_STUDIO_ENABLED': 'true', 'NOVA_STUDIO_ROOT': 'studio',
                                    'NOVA_STUDIO_RUNTIME': 'runtime', 'NOVA_STUDIO_PYTHON': 'runtime/python.exe',
                                    'NOVA_STUDIO_REQUIRED_RAM_MIB': '4096'}, root=tmp_path)
    assert config.studio_root == tmp_path / 'studio'
    assert config.studio_required_ram_bytes == 4*1024**3
    def unexpected(*args, **kwargs): raise AssertionError('model process started during initialization')
    monkeypatch.setattr(subprocess, 'Popen', unexpected)
    core = NovaGatewayCore(lambda *args: ('ok', {}), config=config, register_ollama=False)
    try:
        assert core.studio is not None
        assert core.studio.store.recovery_jobs() == []
        assert core.studio.wan._process is None
    finally:
        core.close_media()


def test_disabled_studio_creates_no_database(tmp_path):
    config = GatewayConfig.from_env({'NOVA_STUDIO_ENABLED': 'false'}, root=tmp_path)
    core = NovaGatewayCore(lambda *args: ('ok', {}), config=config, register_ollama=False)
    assert core.studio is None
    assert not (tmp_path / 'NOVA_LOCAL_VIDEO_STUDIO/state/media.sqlite3').exists()
