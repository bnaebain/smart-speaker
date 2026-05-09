"""
Speech-to-text using faster-whisper (runs locally on the Pi).

Model is downloaded on first use and cached in ~/.cache/huggingface/.
'tiny.en' (~75 MB) is fast enough on RPi 4; swap for 'base.en' for
better accuracy at the cost of ~2x latency.
"""

from faster_whisper import WhisperModel
from config import WHISPER_MODEL

_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        print(f"[stt] Loading Whisper model '{WHISPER_MODEL}' …")
        _model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
        print("[stt] Model ready")
    return _model


def transcribe(wav_path: str) -> str:
    """Return transcribed text from a WAV file, or '' on failure."""
    model = _get_model()
    try:
        segments, _ = model.transcribe(wav_path, language="en", beam_size=1)
        text = " ".join(s.text for s in segments).strip()
        print(f"[stt] '{text}'")
        return text
    except Exception as exc:
        print(f"[stt] Transcription error: {exc}")
        return ""
