"""Ingestion must never trust names, lengths, owners or replaced input files."""
import hashlib
import io
from pathlib import Path
import shutil
import subprocess
import wave

import pytest
from PIL import Image
from nova_gateway.errors import InvalidRequestError, PermissionDeniedError
from nova_gateway.media_store import MediaStore, AssetRecord


def service(tmp_path):
    from nova_gateway.media_assets import AssetService
    probe = shutil.which('ffprobe')
    assert probe, 'Installed FFprobe required for real media validation'
    root = tmp_path / 'studio with spaces'
    return AssetService(root, MediaStore(tmp_path / 'jobs.db'), Path(probe))


def png():
    stream = io.BytesIO()
    Image.new('RGB', (8, 12), 'blue').save(stream, format='PNG')
    return stream.getvalue()


@pytest.mark.parametrize('kind,size', [('image', 25*1024**2+1), ('audio', 250*1024**2+1)])
def test_limits_reject_before_read(tmp_path, kind, size):
    class Unreadable:
        def read(self, n):
            raise AssertionError('oversize body was read')
    with pytest.raises(InvalidRequestError):
        service(tmp_path).ingest('alice', kind, Unreadable(), size)


def test_truncated_upload_not_published(tmp_path):
    app = service(tmp_path)
    with pytest.raises(InvalidRequestError):
        app.ingest('alice', 'image', io.BytesIO(png()), len(png())+4)
    assert not list(app.root.rglob('*.part'))
    assert not list((app.root / 'inputs').rglob('*.png'))


def test_valid_copy_preserves_original_hash(tmp_path):
    app = service(tmp_path)
    original = tmp_path / 'artist & photo.png'
    original.write_bytes(png())
    with original.open('rb') as stream:
        record = app.ingest('alice', 'image', stream, original.stat().st_size)
    assert record.sha256 == hashlib.sha256(png()).hexdigest()
    assert app.resolve(record.id, 'alice').read_bytes() == original.read_bytes() == png()
    assert record.metadata['width'] == 8 and record.metadata['height'] == 12
    with pytest.raises(PermissionDeniedError):
        app.resolve(record.id, 'bob')
    app.resolve(record.id, 'alice').write_bytes(b'replaced')
    with pytest.raises(InvalidRequestError):
        app.resolve(record.id, 'alice')


def test_invalid_media_not_published(tmp_path):
    app = service(tmp_path)
    with pytest.raises(InvalidRequestError):
        app.ingest('alice', 'image', io.BytesIO(b'not an image'), 12)
    assert not list(app.root.rglob('*.part'))


def test_real_audio_validated_without_filename(tmp_path):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as audio:
        audio.setparams((1, 2, 8000, 800, 'NONE', 'not compressed'))
        audio.writeframes(b'\0\0' * 800)
    raw = buf.getvalue()
    app = service(tmp_path)
    record = app.ingest('alice', 'audio', io.BytesIO(raw), len(raw))
    assert record.metadata['duration'] == pytest.approx(.1)
    assert app.resolve(record.id, 'alice').read_bytes() == raw


def test_owner_and_reparse_escape_rejected(tmp_path):
    app = service(tmp_path)
    outside = tmp_path / 'external'
    outside.mkdir()
    (outside / 'a.png').write_bytes(png())
    link = app.root / 'inputs' / 'images' / 'escaped'
    link.parent.mkdir(parents=True, exist_ok=True)
    # Windows directory junctions need no symlink privilege; no destructive shell.
    import os
    if os.name == 'nt':
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)], capture_output=True)
        assert result.returncode == 0, result.stderr
    else:
        link.symlink_to(outside, target_is_directory=True)
    try:
        record = AssetRecord('escape', 'alice', 'image', 'inputs/images/escaped/a.png',
                             hashlib.sha256(png()).hexdigest(), len(png()), {})
        app.store.register_asset(record)
        with pytest.raises(InvalidRequestError):
            app.resolve(record.id, 'alice')
    finally:
        if os.name == 'nt':
            link.rmdir()  # removes only the test junction, not its target
        else:
            link.unlink()
    assert (outside / 'a.png').read_bytes() == png()
