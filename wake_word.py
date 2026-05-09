"""
Wake word detection using openwakeword.

The listener opens a mic stream, feeds 80ms chunks to the model, and
calls on_detected() *after* closing the stream so the recording thread
can immediately open its own stream without device conflicts.
"""

import threading

import numpy as np

from config import WAKE_WORD_MODEL, WAKE_THRESHOLD

try:
    from openwakeword.model import Model as _Model
    _AVAILABLE = True
except Exception:
    _AVAILABLE = False


class WakeWordDetector:
    def __init__(self):
        if not _AVAILABLE:
            print("[wake] openwakeword not installed — button-only mode")
            self._model = None
            return
        print(f"[wake] Loading '{WAKE_WORD_MODEL}' model …")
        self._model = _Model(wakeword_models=[WAKE_WORD_MODEL], inference_framework="onnx")
        print("[wake] Ready")

    @property
    def available(self) -> bool:
        return self._model is not None

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
        chunk = max(256, int(0.08 * native_rate))  # ~80ms
        detected = False

        with sd.RawInputStream(
            samplerate=native_rate,
            channels=1,
            dtype="int16",
            device=device,
            blocksize=chunk,
        ) as stream:
            while not stop_event.is_set():
                data, _ = stream.read(chunk)
                audio = np.frombuffer(bytes(data), dtype=np.int16)
                audio_f = audio.astype(np.float32) / 32768.0
                audio_16k = _resample(audio_f, native_rate, WHISPER_RATE)
                audio_16k_i16 = (audio_16k * 32767).astype(np.int16)

                scores = self._model.predict(audio_16k_i16)
                if scores.get(WAKE_WORD_MODEL, 0.0) >= WAKE_THRESHOLD:
                    self._model.reset()
                    detected = True
                    break  # closes stream on context exit

        if detected and not stop_event.is_set():
            on_detected()
