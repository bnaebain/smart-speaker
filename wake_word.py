"""
Wake word detection.

Priority order:
  1. Picovoice Porcupine  — if PORCUPINE_ACCESS_KEY is set and .ppn file exists
                             (custom "Nova" wake word — create at console.picovoice.ai)
  2. openwakeword          — fallback, uses built-in "hey_jarvis" model
  3. Button-only           — if neither is available

The listener always calls on_detected() AFTER its mic stream closes, so the
recording thread can immediately open its own stream without device conflicts.
"""

import os
import threading

import numpy as np

from config import (
    PORCUPINE_ACCESS_KEY, PORCUPINE_MODEL_PATH,
    WAKE_WORD_MODEL, WAKE_THRESHOLD,
)


def _build_detector():
    """Return the best available detector instance."""
    # --- Porcupine ---
    ppn = os.path.join(os.path.dirname(__file__), PORCUPINE_MODEL_PATH)
    if PORCUPINE_ACCESS_KEY and os.path.exists(ppn):
        try:
            import pvporcupine
            handle = pvporcupine.create(
                access_key=PORCUPINE_ACCESS_KEY,
                keyword_paths=[ppn],
            )
            print(f"[wake] Porcupine ready — say 'Nova'")
            return "porcupine", handle
        except Exception as exc:
            print(f"[wake] Porcupine failed: {exc}")

    # --- openwakeword ---
    try:
        from openwakeword.model import Model
        model = Model(wakeword_models=[WAKE_WORD_MODEL], inference_framework="onnx")
        print(f"[wake] openwakeword ready — say 'Hey Jarvis'")
        return "oww", model
    except Exception as exc:
        print(f"[wake] openwakeword failed: {exc}")

    print("[wake] No wake word engine available — button-only mode")
    return "none", None


class WakeWordDetector:
    def __init__(self):
        self._kind, self._handle = _build_detector()

    @property
    def available(self) -> bool:
        return self._kind != "none"

    def listen(self, on_detected, stop_event: threading.Event):
        """
        Block until wake word heard or stop_event set.
        on_detected() is called AFTER the mic stream closes.
        """
        if not self.available:
            stop_event.wait()
            return

        import sounddevice as sd
        from audio import find_input_device, _device_native_rate, _resample, WHISPER_RATE

        device = find_input_device()
        native_rate = _device_native_rate(device)
        detected = False

        if self._kind == "porcupine":
            target_rate = self._handle.sample_rate       # 16000
            frame_len   = self._handle.frame_length      # 512
            native_chunk = max(256, int(frame_len * native_rate / target_rate))

            with sd.RawInputStream(
                samplerate=native_rate, channels=1, dtype="int16",
                device=device, blocksize=native_chunk,
            ) as stream:
                while not stop_event.is_set():
                    data, _ = stream.read(native_chunk)
                    audio = np.frombuffer(bytes(data), dtype=np.int16)
                    audio_f = audio.astype(np.float32) / 32768.0
                    audio_16k = _resample(audio_f, native_rate, target_rate)
                    frame = (audio_16k[:frame_len] * 32767).astype(np.int16)
                    if len(frame) < frame_len:
                        continue
                    if self._handle.process(frame) >= 0:
                        detected = True
                        break

        else:  # openwakeword
            chunk = max(256, int(0.08 * native_rate))
            with sd.RawInputStream(
                samplerate=native_rate, channels=1, dtype="int16",
                device=device, blocksize=chunk,
            ) as stream:
                while not stop_event.is_set():
                    data, _ = stream.read(chunk)
                    audio = np.frombuffer(bytes(data), dtype=np.int16)
                    audio_f = audio.astype(np.float32) / 32768.0
                    audio_16k = _resample(audio_f, native_rate, WHISPER_RATE)
                    audio_16k_i16 = (audio_16k * 32767).astype(np.int16)
                    scores = self._handle.predict(audio_16k_i16)
                    if scores.get(WAKE_WORD_MODEL, 0.0) >= WAKE_THRESHOLD:
                        self._handle.reset()
                        detected = True
                        break

        if detected and not stop_event.is_set():
            on_detected()
