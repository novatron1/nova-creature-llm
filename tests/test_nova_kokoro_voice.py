import base64
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nova_kokoro_voice import synthesize_to_wav


def test_synthesize_to_wav_returns_cuda_wave_payload():
    class FakeAudio:
        def detach(self):
            return self

        def cpu(self):
            return self

        def numpy(self):
            return self

        def reshape(self, _shape):
            return self

        def tolist(self):
            return [0.0, 0.5, -0.5, 0.0]

    class FakePipeline:
        def __call__(self, text, *, voice, speed):
            assert text == "Hello from Nova"
            assert voice == "af_heart"
            assert speed == 1.0
            yield ("graphemes", "phonemes", FakeAudio())

    payload = synthesize_to_wav(
        "Hello from Nova",
        voice="af_heart",
        pipeline_factory=FakePipeline,
        device="cuda",
    )

    audio = base64.b64decode(payload["audio_base64"])
    assert payload["ok"] is True
    assert payload["device"] == "cuda"
    assert payload["voice_name"] == "af_heart"
    assert payload["mime_type"] == "audio/wav"
    assert audio.startswith(b"RIFF")
    assert b"WAVE" in audio[:16]


def test_windows_launchers_start_the_local_gpu_voice_worker():
    expected = "start_nova_kokoro_voice.ps1"
    assert expected in (ROOT / "START_NOVA_WINDOWS.bat").read_text(encoding="utf-8")
    assert expected in (ROOT / "START_NOVA_ANYWHERE_WINDOWS.bat").read_text(encoding="utf-8")
    defaults = json.loads((ROOT / "nova_llm_config.json").read_text(encoding="utf-8"))
    assert defaults["NOVA_TTS_ENGINE"] == "kokoro_gpu"
    assert defaults["NOVA_TTS_KOKORO_URL"] == "http://127.0.0.1:8890"
