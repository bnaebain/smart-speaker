"""
Audio recording (USB mic) and playback (Pirate Audio I2S DAC).

Recording: sounddevice reads from the first USB input device found at its
           native sample rate, then resamples to WHISPER_RATE for Whisper.
Playback:  mpg123 plays MP3 files; ALSA default output routes to the
           Pirate Audio amp (configured by Pimoroni installer).
"""

import math
import subprocess
import threading
import time

import numpy as np
import sounddevice as sd
import soundfile as sf

from config import CHANNELS, MAX_RECORD_SECONDS, USB_MIC_KEYWORD

WHISPER_RATE = 16000  # Whisper expects 16 kHz


def find_input_device() -> int | None:
    """Return index of first input device whose name contains USB_MIC_KEYWORD."""
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 and USB_MIC_KEYWORD.upper() in dev["name"].upper():
            return i
    return None


def _device_native_rate(device: int | None) -> int:
    """Return the default sample rate reported by the device."""
    info = sd.query_devices(device if device is not None else sd.default.device[0])
    return int(info["default_samplerate"])


def _resample(audio: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    """Resample float32 mono audio using linear interpolation (no scipy needed)."""
    if from_rate == to_rate:
        return audio
    duration = len(audio) / from_rate
    target_len = int(round(duration * to_rate))
    old_indices = np.linspace(0, len(audio) - 1, target_len)
    return np.interp(old_indices, np.arange(len(audio)), audio).astype(np.float32)


def record_until_stop(stop_event: threading.Event) -> np.ndarray | None:
    """
    Record mono audio from the USB mic until stop_event is set or
    MAX_RECORD_SECONDS elapses.

    Returns a float32 numpy array resampled to WHISPER_RATE, or None.
    """
    device = find_input_device()
    native_rate = _device_native_rate(device)
    print(f"[audio] Recording at {native_rate} Hz on device {device}")

    frames: list[np.ndarray] = []
    chunk = 1024

    try:
        with sd.RawInputStream(
            samplerate=native_rate,
            channels=CHANNELS,
            dtype="int16",
            device=device,
            blocksize=chunk,
        ) as stream:
            max_chunks = int(MAX_RECORD_SECONDS * native_rate / chunk)
            for _ in range(max_chunks):
                if stop_event.is_set():
                    break
                data, _ = stream.read(chunk)
                frames.append(np.frombuffer(bytes(data), dtype=np.int16).copy())
    except sd.PortAudioError as exc:
        print(f"[audio] PortAudio error: {exc}")
        return None

    if not frames:
        return None

    raw = np.concatenate(frames).astype(np.float32) / 32768.0
    return _resample(raw, native_rate, WHISPER_RATE)


def save_wav(audio: np.ndarray, path: str) -> None:
    """Write float32 mono array (at WHISPER_RATE) to a WAV file."""
    sf.write(path, audio, WHISPER_RATE, subtype="PCM_16")


def play_mp3(path: str, cancel_event: threading.Event | None = None) -> None:
    """
    Play an MP3 via mpg123 on the default ALSA output (Pirate Audio).
    Blocks until playback finishes.  If cancel_event is set, kills early.
    """
    proc = subprocess.Popen(
        ["mpg123", "-q", path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if cancel_event is None:
        proc.wait()
        return

    while proc.poll() is None:
        if cancel_event.is_set():
            proc.terminate()
            proc.wait()
            return
        time.sleep(0.1)
