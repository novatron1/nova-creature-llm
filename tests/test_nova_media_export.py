"""Real FFmpeg exports, not mocks of the encoder or resulting media metadata."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest
from nova_gateway.errors import InvalidRequestError
from nova_gateway.media_store import JobRecord


@pytest.fixture
def media(tmp_path):
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    assert ffmpeg and ffprobe, 'FFmpeg and FFprobe required'
    video, audio = tmp_path / 'motion & ref.mp4', tmp_path / 'voice ; test.wav'
    subprocess.run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=64x80:rate=24',
                    '-frames:v', '17', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-output_ts_offset', '5', str(video)], check=True)
    subprocess.run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=24000',
                    '-t', '0.25', str(audio)], check=True)
    return tmp_path, Path(ffmpeg), Path(ffprobe), video, audio


@pytest.mark.parametrize('preset,size', [('source', (64, 80)), ('vertical', (720, 1280))])
def test_real_export_normalizes_timestamps_and_pads_short_audio(media, preset, size):
    from nova_gateway.media_export import MediaExporter
    root, ffmpeg, ffprobe, video, audio = media
    before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (video, audio)]
    exporter = MediaExporter(root, ffmpeg, ffprobe)
    job = JobRecord('job1', 'alice', 'k', {'export_preset': preset, 'audio_start_seconds': 0})
    record = exporter.export(job, video, audio, None)
    result = exporter.verify(root / record.relative_path, expected_audio=True)
    v = next(s for s in result['streams'] if s['codec_type'] == 'video')
    a = next(s for s in result['streams'] if s['codec_type'] == 'audio')
    assert (v['width'], v['height']) == size
    assert v['codec_name'] == 'h264' and v['pix_fmt'] == 'yuv420p' and a['codec_name'] == 'aac'
    assert float(v['start_time']) == pytest.approx(0, abs=.001)
    assert float(a['start_time']) == pytest.approx(0, abs=.001)
    assert float(v['duration']) == pytest.approx(17/24, abs=1/24)
    assert abs(float(v['duration']) - float(a['duration'])) <= 1/24 + 1024/24000
    assert [hashlib.sha256(p.read_bytes()).hexdigest() for p in (video, audio)] == before
    manifest = json.loads((root / record.relative_path).with_name('manifest.json').read_text())
    assert manifest['native_dimensions'] == [64, 80]
    assert 'not audio-driven' in manifest['label']


def test_bad_segment_or_failed_export_preserves_previous(media):
    from nova_gateway.media_export import MediaExporter
    root, ffmpeg, ffprobe, video, audio = media
    exporter = MediaExporter(root, ffmpeg, ffprobe)
    previous = exporter.export(JobRecord('job1', 'a', 'k', {}), video, None, None)
    old_bytes = (root / previous.relative_path).read_bytes()
    with pytest.raises(InvalidRequestError):
        exporter.export(JobRecord('job1', 'a', 'k', {'audio_start_seconds': 100}), video, audio, None)
    corrupt = root / 'corrupt.mp4'
    corrupt.write_bytes(b'broken')
    with pytest.raises(InvalidRequestError):
        exporter.export(JobRecord('job1', 'a', 'k', {}), corrupt, None, None)
    assert (root / previous.relative_path).read_bytes() == old_bytes


def test_optional_beat_is_mixed_into_export(media):
    from nova_gateway.media_export import MediaExporter
    root, ffmpeg, ffprobe, video, audio = media
    exporter = MediaExporter(root, ffmpeg, ffprobe)
    record = exporter.export(JobRecord('mix', 'a', 'k', {}), video, audio, audio)
    manifest = json.loads((root / record.relative_path).with_name('manifest.json').read_text())
    assert 'amix' in manifest['audio_filter']
    assert exporter.verify(root / record.relative_path, True)['streams']


def test_stock_voice_is_lazy_and_waits_for_subprocess(tmp_path, monkeypatch):
    from nova_gateway.media_export import StockVoice
    root = tmp_path / 'studio'
    (root / '.venv-tts/Scripts').mkdir(parents=True)
    (root / '.venv-tts/Scripts/python.exe').write_bytes(b'fixture')
    (root / 'scripts').mkdir()
    (root / 'scripts/make_voice.py').write_text('')
    def forbidden(*args, **kwargs):
        raise AssertionError('TTS started at construction')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    voice = StockVoice(root)
    generated = root / 'inputs/audio/spoken.wav'
    generated.parent.mkdir(parents=True)
    def run(command, **kwargs):
        assert command[-1] == 'spoken preview'
        assert kwargs['timeout'] > 0 and not kwargs.get('shell')
        generated.write_bytes(b'generated audio fixture')
        return subprocess.CompletedProcess(command, 0, str(generated)+'\n', '')
    monkeypatch.setattr(subprocess, 'run', run)
    target = root / 'inputs/audio/managed.wav'
    assert voice.render('spoken preview', target).read_bytes() == b'generated audio fixture'


def test_cancelled_export_command_stops_only_its_child(tmp_path):
    from nova_gateway.media_export import MediaExporter, MediaCancelledError
    from threading import Event, Timer
    import sys
    import time
    exporter = MediaExporter(tmp_path, Path('unused'), Path('unused'))
    cancelled = Event()
    timer = Timer(.2, cancelled.set)
    started = time.monotonic()
    timer.start()
    try:
        with pytest.raises(MediaCancelledError):
            exporter._run([sys.executable, '-c', 'import time; time.sleep(30)'], cancel_event=cancelled)
    finally:
        timer.join()
    assert time.monotonic() - started < 5
