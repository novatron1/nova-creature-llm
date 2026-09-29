"""Durable local MP4 exports. Audio overlay is never represented as lip-sync."""
from __future__ import annotations

from dataclasses import asdict
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
from threading import Event
import time
from uuid import uuid4

from .errors import InvalidRequestError
from .media_assets import contained_path, file_hash
from .media_store import JobRecord, OutputRecord

OVERLAY_LABEL = 'generated motion + audio overlay — not audio-driven animation or verified lip-sync'


class MediaCancelledError(InvalidRequestError):
    def __init__(self):
        super().__init__('Media operation cancelled.')


class MediaExporter:
    def __init__(self, root: Path, ffmpeg: Path, ffprobe: Path):
        self.root = Path(root).resolve()
        self.ffmpeg, self.ffprobe = Path(ffmpeg), Path(ffprobe)

    def _run(self, command: list[str], timeout: int = 120, *, cancel_event: Event | None = None):
        process = None
        try:
            if cancel_event is not None and cancel_event.is_set():
                raise MediaCancelledError()
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            deadline = time.monotonic() + timeout
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise MediaCancelledError()
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(command, timeout)
                try:
                    stdout, stderr = process.communicate(timeout=.2)
                    break
                except subprocess.TimeoutExpired:
                    continue
            result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            if result.returncode:
                raise InvalidRequestError('Media command failed: ' + result.stderr.decode(errors='replace')[-1500:])
            return result
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise InvalidRequestError('Local media command failed or timed out.') from exc
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()  # only the child created in this method
                process.communicate()

    def _probe(self, path: Path) -> dict:
        result = self._run([str(self.ffprobe), '-v', 'error', '-protocol_whitelist', 'file,pipe',
                            '-show_entries', 'format=duration:stream=codec_type,codec_name,pix_fmt,width,height,start_time,duration,r_frame_rate,sample_rate,nb_frames',
                            '-of', 'json', str(path)], 30)
        try:
            return json.loads(result.stdout)
        except ValueError as exc:
            raise InvalidRequestError('FFprobe returned invalid metadata.') from exc

    @staticmethod
    def _duration(stream: dict) -> float:
        try:
            duration = float(stream['duration'])
            if not math.isfinite(duration) or duration <= 0:
                raise ValueError('duration')
            return duration
        except (ValueError, KeyError, TypeError) as exc:
            raise InvalidRequestError('Media stream has no finite positive duration.') from exc

    def verify(self, path: Path, expected_audio: bool) -> dict:
        info = self._probe(path)
        videos = [s for s in info.get('streams', []) if s.get('codec_type') == 'video']
        audios = [s for s in info.get('streams', []) if s.get('codec_type') == 'audio']
        if len(videos) != 1 or bool(audios) != expected_audio or len(audios) > 1:
            raise InvalidRequestError('Export does not contain the expected video/audio streams.')
        video = videos[0]
        if video.get('codec_name') != 'h264' or video.get('pix_fmt') != 'yuv420p':
            raise InvalidRequestError('Export is not compatible H.264/yuv420p.')
        duration = self._duration(video)
        try:
            fps = float(Fraction(video['r_frame_rate']))
            if not math.isfinite(fps) or fps <= 0:
                raise ValueError('fps')
            if abs(float(video.get('start_time', 0))) > 1/fps:
                raise ValueError('video start')
            if audios:
                audio = audios[0]
                sample_rate = int(audio['sample_rate'])
                tolerance = 1/fps + 1024/sample_rate
                if (audio.get('codec_name') != 'aac' or abs(float(audio.get('start_time', 0))) > tolerance
                        or abs(self._duration(audio) - duration) > tolerance):
                    raise ValueError('audio synchronization')
        except (ValueError, KeyError, ZeroDivisionError) as exc:
            raise InvalidRequestError('Export timing or audio compatibility check failed.') from exc
        self._run([str(self.ffmpeg), '-v', 'error', '-xerror', '-i', str(path), '-f', 'null', '-'])
        return info

    def export(self, job: JobRecord, video: Path, vocal: Path | None, beat: Path | None, *, cancel_event: Event | None = None) -> OutputRecord:
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', job.id):
            raise InvalidRequestError('Invalid export job identity.')
        preset = job.request.get('export_preset', 'source')
        if preset not in ('source', 'vertical'):
            raise InvalidRequestError('Unsupported video export preset.')
        streams = self._probe(video).get('streams', [])
        source_video = next((s for s in streams if s.get('codec_type') == 'video'), None)
        if source_video is None:
            raise InvalidRequestError('Source has no video stream.')
        duration = self._duration(source_video)
        if duration > 5.05:
            raise InvalidRequestError('This preview exporter supports clips up to five seconds.')
        try:
            start = float(job.request.get('audio_start_seconds', 0))
            if not math.isfinite(start) or start < 0:
                raise ValueError('start')
        except (ValueError, TypeError) as exc:
            raise InvalidRequestError('Invalid audio segment start.') from exc
        inputs = [p for p in (vocal, beat) if p is not None]
        for path in inputs:
            audio_info = self._probe(path)
            audio_stream = next((s for s in audio_info.get('streams', []) if s.get('codec_type') == 'audio'), None)
            if audio_stream is None:
                raise InvalidRequestError('Selected audio has no audio stream.')
            # WAV/MP3 stream duration is sometimes on the container only.
            audio_duration = self._duration(audio_stream if audio_stream.get('duration') else audio_info.get('format', {}))
            if start >= audio_duration:
                raise InvalidRequestError('Audio segment starts beyond the recording.')
        output_id = uuid4().hex
        parent = contained_path(self.root, f'outputs/final/{job.id}')
        parent.mkdir(parents=True, exist_ok=True)
        temporary = parent / ('.pending-' + output_id)
        temporary.mkdir()
        final = parent / output_id
        path = temporary / 'video.mp4'
        audio_filter = ''
        try:
            command = [str(self.ffmpeg), '-v', 'error', '-nostdin', '-i', str(video)]
            for audio in inputs:
                command += ['-i', str(audio)]
            vf = 'setpts=PTS-STARTPTS,setsar=1'
            if preset == 'vertical':
                vf += ',scale=720:1280:force_original_aspect_ratio=decrease:force_divisible_by=2,pad=720:1280:(ow-iw)/2:(oh-ih)/2'
            command += ['-vf', vf, '-map', '0:v:0']
            if inputs:
                filters = [f'[{n}:a:0]atrim=start={start:.6f},asetpts=PTS-STARTPTS,apad,atrim=duration={duration:.9f}[a{n}]'
                           for n in range(1, len(inputs)+1)]
                if len(inputs) == 2:
                    filters.append('[a1][a2]amix=inputs=2:duration=longest:normalize=1,alimiter=limit=0.95:level=0:latency=1[aout]')
                    audio_label = '[aout]'
                else:
                    audio_label = '[a1]'
                audio_filter = ';'.join(filters)
                command += ['-filter_complex', audio_filter, '-map', audio_label, '-c:a', 'aac', '-b:a', '192k']
            else:
                command += ['-an']
            command += ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-preset', 'veryfast',
                        '-t', f'{duration:.9f}', '-movflags', '+faststart', str(path)]
            self._run(command, cancel_event=cancel_event)
            verified = self.verify(path, bool(inputs))
            if cancel_event is not None and cancel_event.is_set():
                raise MediaCancelledError()
            metadata = {'native_dimensions': [source_video['width'], source_video['height']],
                        'export_preset': preset, 'streams': verified['streams'],
                        'audio_filter': audio_filter, 'video_filter': vf,
                        'label': OVERLAY_LABEL if inputs else 'generated motion — no audio',
                        'request': job.request}
            relative = (final / 'video.mp4').relative_to(self.root).as_posix()
            record = OutputRecord(output_id, relative, file_hash(path), path.stat().st_size, metadata)
            manifest = {**metadata, 'output': asdict(record)}
            with (temporary / 'manifest.json').open('x', encoding='utf-8') as output:
                json.dump(manifest, output, indent=2, allow_nan=False)
                output.flush()
                os.fsync(output.fileno())
            temporary.rename(final)
            return record
        finally:
            # Only remove the two exact files this export created, never a tree.
            if temporary.exists():
                for name in ('video.mp4', 'manifest.json'):
                    (temporary / name).unlink(missing_ok=True)
                temporary.rmdir()


class StockVoice:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def render(self, text: str, destination: Path) -> Path:
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise InvalidRequestError('Provide 1 to 2000 characters of spoken-preview text.')
        try:
            relative = Path(destination).absolute().relative_to(self.root).as_posix()
        except ValueError as exc:
            raise InvalidRequestError('Voice output must stay inside the studio.') from exc
        destination = contained_path(self.root, relative)
        python = self.root / '.venv-tts/Scripts/python.exe'
        script = self.root / 'scripts/make_voice.py'
        if not python.is_file() or not script.is_file():
            raise InvalidRequestError('Local stock voice is not installed.')
        try:
            result = subprocess.run([str(python), str(script), text], capture_output=True, text=True,
                                    timeout=180, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode:
                raise InvalidRequestError('Stock spoken preview failed; use your recording instead.')
            source = Path(result.stdout.strip().splitlines()[-1])
            source = contained_path(self.root, source.relative_to(self.root).as_posix())
            if not source.is_relative_to(self.root / 'inputs/audio') or not source.is_file():
                raise ValueError('voice output')
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source.open('rb') as incoming, destination.open('xb') as outgoing:
                shutil.copyfileobj(incoming, outgoing)
            return destination
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as exc:
            raise InvalidRequestError('Local spoken preview could not be produced.') from exc
