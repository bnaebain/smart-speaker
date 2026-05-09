"""
Audio recording (USB mic) and playback (Pirate Audio I2S DAC).

Recording: sounddevice reads from the first USB input device found.
Playback:  mpg123 plays MP3 files; ALSA default output routes to the
           Pirate Audio amp (configured by Pimoroni installer).
"""

import subprocess
import tempfile
import threading

import numpy as np
import sounddevice as sd
import soundfile as sf

from config import SAMPLE_RATE, CHANNELS, MAX_RECORD_SECONDS, USB_MIC_KEYWORD


def find_input_device() -> int | None:
    """Return index of first input device whose name contains USB_MIC_KEYWORD."""
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 and USB_MIC_KEYWORD.upper() in dev["name"].upper():
            return i
    return None  # falls back to system default


def record_until_stop(stop_event: threading.Event) -> np.ndarray | None:
    """
    Record 16-bit mono audio from the USB mic until stop_event is set
    or MAX_RECORD_SECONDS elapses.

    Returns a float32 numpy array at SAMPLE_RATE, or None if nothing captured.
    """
    device = find_input_device()
    frames: list[np.ndarray] = []
    chunk = 1024

    try:
        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            device=device,
            blocksize=chunk,
        ) as stream:
            max_chunks = int(MAX_RECORD_SECONDS * SAMPLE_RATE / chunk)
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
    return raw


def save_wav(audio: np.ndarray, path: str) -> None:
    """Write float32 mono array to a WAV file."""
    sf.write(path, audio, SAMPLE_RATE, subtype="PCM_16")


def play_mp3(path: str, cancel_event: threading.Event | None = None) -> None:
    """
    Play an MP3 via mpg123 on the default ALSA output (Pirate Audio).
    Blocks until playback finishes.  If cancel_event is set mid-play,
    the process is killed.
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
        # poll every 100 ms
        import time
        time.sleep(0.1)
