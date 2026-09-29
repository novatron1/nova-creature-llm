"""Bounded copies of user media; originals never become mutable job inputs."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path, PureWindowsPath
import stat
import subprocess
from typing import BinaryIO
from uuid import uuid4

from .errors import InvalidRequestError
from .media_store import AssetRecord, MediaStore


def contained_path(root: Path, relative: str) -> Path:
    """Reject traversal and reparse components, including in-root junctions."""
    rel = Path(relative)
    if (not relative or rel.is_absolute() or PureWindowsPath(relative).drive
            or '..' in rel.parts or '\\' in relative or ':' in relative):
        raise InvalidRequestError('Invalid managed media path.')
    current = root
    for part in rel.parts:
        current = current / part
        try:
            attrs = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(attrs.st_mode) or getattr(attrs, 'st_file_attributes', 0) & 0x400:
            raise InvalidRequestError('Linked media paths are not allowed.')
    if not current.resolve().is_relative_to(root.resolve()):
        raise InvalidRequestError('Media path escapes the studio.')
    return current


def file_hash(path: Path) -> str:
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


class AssetService:
    LIMITS = {'image': 25 * 1024**2, 'audio': 250 * 1024**2}

    def __init__(self, root: Path, store: MediaStore, ffprobe: Path):
        self.root = Path(root).resolve()
        self.store = store
        self.ffprobe = Path(ffprobe)

    def ingest(self, owner_id: str, kind: str, stream: BinaryIO, content_length: int) -> AssetRecord:
        if (kind not in self.LIMITS or type(content_length) is not int
                or not 0 < content_length <= self.LIMITS[kind]):
            raise InvalidRequestError('Invalid or oversized media upload.')
        if not isinstance(owner_id, str) or not owner_id.strip() or len(owner_id) > 200:
            raise InvalidRequestError('A media owner is required.')
        asset_id = uuid4().hex
        directory = contained_path(self.root, 'inputs/images' if kind == 'image' else 'inputs/audio')
        directory.mkdir(parents=True, exist_ok=True)
        relative_base = directory.relative_to(self.root).as_posix() + '/' + asset_id
        temporary = contained_path(self.root, relative_base + '.part')
        published = None
        try:
            with temporary.open('xb') as output:
                remaining = content_length
                while remaining:
                    chunk = stream.read(min(1024*1024, remaining))
                    if not chunk or len(chunk) > remaining:
                        raise InvalidRequestError('Media upload was truncated or malformed.')
                    output.write(chunk)
                    remaining -= len(chunk)
                output.flush()
                os.fsync(output.fileno())
            suffix, metadata = self._validate(temporary, kind)
            relative = relative_base + suffix
            destination = contained_path(self.root, relative)
            record = AssetRecord(asset_id, owner_id, kind, relative, file_hash(temporary),
                                 content_length, metadata)
            temporary.rename(destination)
            published = destination
            self.store.register_asset(record)
            return record
        except BaseException:
            if published is not None:
                published.unlink(missing_ok=True)
            raise
        finally:
            temporary.unlink(missing_ok=True)

    def _validate(self, path: Path, kind: str) -> tuple[str, dict]:
        if kind == 'image':
            from PIL import Image, UnidentifiedImageError
            try:
                with Image.open(path) as image:
                    if image.format not in ('PNG', 'JPEG', 'WEBP') or image.width * image.height > 40_000_000:
                        raise InvalidRequestError('Use a PNG, JPEG or WebP image up to 40 megapixels.')
                    suffix = {'PNG': '.png', 'JPEG': '.jpg', 'WEBP': '.webp'}[image.format]
                    metadata = {'width': image.width, 'height': image.height, 'format': image.format}
                    if getattr(image, 'n_frames', 1) != 1:
                        raise InvalidRequestError('Use a single still reference image.')
                    image.verify()
                with Image.open(path) as image:
                    image.load()
                return suffix, metadata
            except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
                raise InvalidRequestError('Reference image could not be decoded.') from exc
        with path.open('rb') as source:
            header = source.read(12)
        # Only simple audio containers; reject playlists before invoking FFprobe.
        if header.startswith(b'RIFF') and header[8:12] == b'WAVE':
            suffix = '.wav'
        elif header.startswith(b'fLaC'):
            suffix = '.flac'
        elif header.startswith(b'OggS'):
            suffix = '.ogg'
        elif header.startswith(b'ID3') or (len(header) > 1 and header[0] == 255 and header[1] & 0xE0 == 0xE0):
            suffix = '.mp3'
        else:
            raise InvalidRequestError('Use WAV, MP3, FLAC or Ogg audio.')
        try:
            result = subprocess.run([str(self.ffprobe), '-v', 'error', '-protocol_whitelist', 'file,pipe',
                                     '-show_entries', 'format=duration:stream=codec_type,sample_rate,channels',
                                     '-of', 'json', str(path)], capture_output=True, timeout=30,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            info = json.loads(result.stdout)
            duration = float(info['format']['duration'])
            streams = info.get('streams', [])
            if result.returncode or not math.isfinite(duration) or duration <= 0 or not streams:
                raise ValueError('invalid audio')
            if any(s.get('codec_type') != 'audio' for s in streams):
                raise ValueError('audio-only input required')
            return suffix, {'duration': duration, 'streams': streams}
        except (OSError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
            raise InvalidRequestError('Audio could not be validated by FFprobe.') from exc

    def resolve(self, asset_id: str, owner_id: str) -> Path:
        record = self.store.get_asset(asset_id, owner_id)
        path = contained_path(self.root, record.relative_path)
        try:
            if not path.is_file() or path.stat().st_size != record.size_bytes or file_hash(path) != record.sha256:
                raise InvalidRequestError('Managed media is missing or has changed.')
        except OSError as exc:
            raise InvalidRequestError('Managed media is unavailable.') from exc
        return path
