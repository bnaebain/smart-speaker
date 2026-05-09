"""
Audio recording (USB mic) and playback (Pirate Audio I2S DAC).

Recording: sounddevice reads from the first USB input device found at its
           native sample rate, then resamples to WHISPER_RATE for Whisper.
Playback:  mpg123 plays MP3 files; ALSA default output routes to the
           Pirate Audio amp (set via /etc/asound.conf by install.sh).
"""

import subprocess
import threading
import time

import numpy as np
import sounddevice as sd
import soundfile as sf

from config import CHANNELS, MAX_RECORD_SECONDS, USB_MIC_KEYWORD, SILENCE_TIMEOUT, SPEECH_THRESHOLD, SILENCE_THRESHOLD

WHISPER_RATE = 16000


def find_input_device() -> int | None:
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 and USB_MIC_KEYWORD.upper() in dev["name"].upper():
            return i
    return None


def _device_native_rate(device: int | None) -> int:
    info = sd.query_devices(device if device is not None else sd.default.device[0])
    return int(info["default_samplerate"])


def _resample(audio: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    if from_rate == to_rate:
        return audio
    target_len = int(round(len(audio) * to_rate / from_rate))
    old_idx = np.linspace(0, len(audio) - 1, target_len)
    return np.interp(old_idx, np.arange(len(audio)), audio).astype(np.float32)


def _open_stream(device, native_rate, chunk):
    return sd.RawInputStream(
        samplerate=native_rate,
        channels=CHANNELS,
        dtype="int16",
        device=device,
        blocksize=chunk,
    )


def record_until_stop(stop_event: threading.Event) -> np.ndarray | None:
    """Push-to-talk: record until stop_event set. Returns 16kHz float32 array."""
    device = find_input_device()
    native_rate = _device_native_rate(device)
    chunk = 1024
    frames = []
    print(f"[audio] PTT recording at {native_rate} Hz")
    try:
        with _open_stream(device, native_rate, chunk) as stream:
            for _ in range(int(MAX_RECORD_SECONDS * native_rate / chunk)):
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


def record_with_vad(cancel_event: threading.Event,
                    stop_early: threading.Event | None = None) -> np.ndarray | None:
    """Wake-word mode: record until silence, cancel, or stop_early (button A).
    Uses two thresholds: SPEECH_THRESHOLD to detect talking, SILENCE_THRESHOLD
    to detect when the room is quiet again."""
    device = find_input_device()
    native_rate = _device_native_rate(device)
    chunk = 1024
    frames = []
    silent_chunks = 0
    max_silent = int(SILENCE_TIMEOUT * native_rate / chunk)
    has_speech = False
    print(f"[audio] VAD recording at {native_rate} Hz")
    try:
        with _open_stream(device, native_rate, chunk) as stream:
            for _ in range(int(MAX_RECORD_SECONDS * native_rate / chunk)):
                if cancel_event.is_set():
                    return None
                if stop_early and stop_early.is_set():
                    break
                data, _ = stream.read(chunk)
                arr = np.frombuffer(bytes(data), dtype=np.int16)
                frames.append(arr.copy())
                rms = np.sqrt(np.mean((arr.astype(np.float32) / 32768.0) ** 2))
                if rms > SPEECH_THRESHOLD:
                    has_speech = True
                    silent_chunks = 0
                elif has_speech and rms < SILENCE_THRESHOLD:
                    silent_chunks += 1
                    if silent_chunks >= max_silent:
                        break
    except sd.PortAudioError as exc:
        print(f"[audio] PortAudio error: {exc}")
        return None
    if not frames or not has_speech:
        return None
    raw = np.concatenate(frames).astype(np.float32) / 32768.0
    return _resample(raw, native_rate, WHISPER_RATE)


def save_wav(audio: np.ndarray, path: str) -> None:
    sf.write(path, audio, WHISPER_RATE, subtype="PCM_16")


def play_beep(freq: int = 880, duration: float = 0.15) -> None:
    """Short confirmation tone through the default ALSA output (Pirate Audio)."""
    rate = 44100
    t = np.linspace(0, duration, int(rate * duration), endpoint=False)
    wave = (np.sin(2 * np.pi * freq * t) * 0.4 * np.linspace(1.0, 0.0, int(rate * duration))).astype(np.float32)
    sd.play(wave, samplerate=rate)
    sd.wait()


def play_mp3(path: str, cancel_event: threading.Event | None = None) -> None:
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
