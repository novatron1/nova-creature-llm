"""Read-only short-MP4 checks. Frame differences do not prove identity or lip-sync."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from nova_gateway.media_export import MediaExporter
from nova_gateway.media_assets import file_hash


def inspect_video(path: Path, expect_audio: bool) -> dict:
    from PIL import Image, ImageChops, ImageStat
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        raise ValueError('FFmpeg and FFprobe must be installed.')
    path = path.resolve(strict=True)
    exporter = MediaExporter(path.parent, Path(ffmpeg), Path(ffprobe))
    info = exporter.verify(path, expected_audio=expect_audio)
    video = next(stream for stream in info['streams'] if stream['codec_type'] == 'video')
    if float(video['duration']) > 5.05:
        raise ValueError('This checker is limited to five-second previews.')
    result = subprocess.run([ffmpeg, '-v', 'error', '-protocol_whitelist', 'file,pipe', '-i', str(path),
                             '-map', '0:v:0', '-vf', 'scale=160:160', '-frames:v', '121',
                             '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'],
                            capture_output=True, timeout=60,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise ValueError('Frame decode failed.')
    frame_size = 160*160*3
    if len(result.stdout) % frame_size or len(result.stdout) < frame_size*2:
        raise ValueError('Video has fewer than two valid decoded frames.')
    first = Image.frombytes('RGB', (160, 160), result.stdout[:frame_size])
    scores = []
    for start in range(frame_size, len(result.stdout), frame_size):
        frame = Image.frombytes('RGB', (160, 160), result.stdout[start:start+frame_size])
        scores.append(sum(ImageStat.Stat(ImageChops.difference(first, frame)).mean) / 3)
    if max(scores) <= .5:
        raise ValueError('Decoded frames are effectively still; useful motion is not demonstrated.')
    return {'ok': True, 'path': str(path), 'sha256': file_hash(path), 'streams': info['streams'],
            'decoded_frame_count': len(result.stdout)//frame_size,
            'max_mean_pixel_change': max(scores), 'semantic_review_required': True,
            'limitations': 'Changing decoded frames only. Inspect character identity, artifacts and true performance motion separately; audio presence is not lip-sync proof.'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', required=True, type=Path)
    parser.add_argument('--expect-audio', action='store_true')
    args = parser.parse_args()
    try:
        report = inspect_video(args.video, args.expect_audio)
    except Exception as exc:
        report = {'ok': False, 'error': str(exc), 'semantic_review_required': True}
    print(json.dumps(report, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
