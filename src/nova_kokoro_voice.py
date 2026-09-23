"""Small, private Kokoro speech core used by Nova's local GPU worker."""

from __future__ import annotations

import base64
import io
import struct
import wave
from typing import Callable


SAMPLE_RATE = 24_000


def _audio_samples(audio) -> list[float]:
    value = audio
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    if hasattr(value, "reshape"):
        value = value.reshape(-1)
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [float(sample) for sample in value]


def _wav_bytes(samples: list[float]) -> bytes:
    frames = b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, sample)) * 32767))
        for sample in samples
    )
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(frames)
    return output.getvalue()


def synthesize_to_wav(
    text: str,
    *,
    voice: str,
    pipeline_factory: Callable,
    device: str,
    speed: float = 1.0,
) -> dict:
    """Generate a base64 WAV payload from one reusable Kokoro pipeline."""
    spoken = str(text or "").strip()
    if not spoken:
        raise ValueError("No speakable text")
    pipeline = pipeline_factory()
    samples: list[float] = []
    for _, _, audio in pipeline(spoken, voice=voice, speed=float(speed)):
        if audio is not None:
            samples.extend(_audio_samples(audio))
    if not samples:
        raise RuntimeError("Kokoro produced no audio")
    return {
        "ok": True,
        "audio_base64": base64.b64encode(_wav_bytes(samples)).decode("ascii"),
        "mime_type": "audio/wav",
        "voice_name": voice,
        "device": device,
        "sample_rate": SAMPLE_RATE,
    }
