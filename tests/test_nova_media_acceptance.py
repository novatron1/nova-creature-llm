"""Read-only acceptance CLI must reject still video and absent expected audio."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.parametrize('source,audio_expected,accepted', [
    ('color=c=blue:size=64x80:rate=24', False, False),
    ('testsrc2=size=64x80:rate=24', True, False),
    ('testsrc2=size=64x80:rate=24', False, True),
])
def test_acceptance_checks_decoded_motion_and_expected_audio(tmp_path, source, audio_expected, accepted):
    ffmpeg = shutil.which('ffmpeg')
    assert ffmpeg
    video = tmp_path / 'acceptance.mp4'
    subprocess.run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', source, '-frames:v', '17',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)], check=True)
    command = [sys.executable, str(Path(__file__).resolve().parents[1] / 'tools/check_nova_media_pipeline.py'), '--video', str(video)]
    if audio_expected: command.append('--expect-audio')
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert result.stdout, result.stderr
    report = json.loads(result.stdout)
    assert report['ok'] is accepted
    assert (result.returncode == 0) is accepted
    if accepted:
        assert report['decoded_frame_count'] == 17
        assert report['semantic_review_required'] is True
