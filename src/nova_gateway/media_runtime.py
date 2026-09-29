"""Compose already installed media tools; never install or load models here."""
from pathlib import Path
import shutil

from .errors import ProviderUnavailableError
from .media_assets import AssetService
from .media_coordinator import MediaCoordinator
from .media_export import MediaExporter, StockVoice
from .media_resources import ResourceGate
from .media_store import MediaStore
from .media_wan import WanAdapter


def build_media_coordinator(config) -> MediaCoordinator:
    ffmpeg = str(config.video_lite_ffmpeg_path or shutil.which('ffmpeg') or '')
    ffprobe = shutil.which('ffprobe')
    if not ffmpeg or not ffprobe or not config.studio_python or not config.studio_runtime:
        raise ProviderUnavailableError('Configure the installed studio runtime, Python, FFmpeg and FFprobe first.')
    root = config.studio_root.resolve()
    store = MediaStore(root / 'state/media.sqlite3')
    assets = AssetService(root, store, Path(ffprobe))
    gate = ResourceGate(root, store)
    return MediaCoordinator(store, assets, gate,
                            WanAdapter(root, config.studio_runtime, config.studio_python, gate),
                            MediaExporter(root, Path(ffmpeg), Path(ffprobe)), StockVoice(root),
                            required_ram_bytes=config.studio_required_ram_bytes)
