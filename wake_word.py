"""
Wake word detection.

Priority order:
  1. Picovoice Porcupine  — if PORCUPINE_ACCESS_KEY set + .ppn file exists
  2. Whisper keyword       — free, uses existing Whisper model (~2-3s latency)
  3. Button-only           — if nothing else works

Whisper mode: waits for audio energy above threshold, records up to 2s,
runs Whisper tiny, triggers if the configured keyword appears in the transcript.
No extra models or accounts needed.
"""

import os
import tempfile
import threading

import numpy as np

from config import (
    PORCUPINE_ACCESS_KEY, PORCUPINE_MODEL_PATH,
    WAKE_WORD_MODEL, WAKE_THRESHOLD,
    ENERGY_THRESHOLD,  # used as base for wake sensitivity
)

# The keyword Whisper listens for (case-insensitive)
WHISPER_KEYWORD = os.environ.get("WAKE_KEYWORD", "nova")


def _try_porcupine():
    ppn = os.path.join(os.path.dirname(__file__), PORCUPINE_MODEL_PATH)
    if not (PORCUPINE_ACCESS_KEY and os.path.exists(ppn)):
        return None
    try:
        import pvporcupine
        handle = pvporcupine.create(access_key=PORCUPINE_ACCESS_KEY, keyword_paths=[ppn])
        print(f"[wake] Porcupine ready — say '{PORCUPINE_MODEL_PATH.split('_')[0].title()}'")
        return ("porcupine", handle)
    except Exception as exc:
        print(f"[wake] Porcupine failed: {exc}")
    return None


def _try_oww():
    try:
        from openwakeword.model import Model
        model = Model(wakeword_models=[WAKE_WORD_MODEL], inference_framework="onnx")
        print(f"[wake] openwakeword ready — say 'Hey Jarvis'")
        return ("oww", model)
    except Exception:
        return None


class WakeWordDetector:
    def __init__(self):
        result = _try_porcupine()
        if result:
            self._kind, self._handle = result
            return

        # Whisper keyword mode — always available since we already have Whisper
        try:
            import stt  # noqa: F401 — just verify it imports
            self._kind = "whisper"
            self._handle = None
            print(f"[wake] Whisper keyword mode — say '{WHISPER_KEYWORD.upper()}' (~2-3s detection)")
            return
        except Exception:
            pass

        result = _try_oww()
        if result:
            self._kind, self._handle = result
            return

        self._kind = "none"
        self._handle = None
        print("[wake] No wake word engine — button-only mode")

    @property
    def available(self) -> bool:
        return self._kind != "none"

    def listen(self, on_detected, stop_event: threading.Event):
        """Block until wake word heard or stop_event set.
        on_detected() is called AFTER the mic stream closes."""
        if not self.available:
            stop_event.wait()
            return

        if self._kind == "porcupine":
            self._listen_porcupine(on_detected, stop_event)
        elif self._kind == "whisper":
            self._listen_whisper(on_detected, stop_event)
        else:
            self._listen_oww(on_detected, stop_event)

    # ------------------------------------------------------------------

    def _listen_whisper(self, on_detected, stop_event):
        print("[wake] _listen_whisper started")
        try:
            import sounddevice as sd
            import soundfile as sf
            from audio import find_input_device, _device_native_rate, _resample, WHISPER_RATE
            import stt
        except Exception as exc:
            print(f"[wake] import error: {exc}")
            return

        try:
            device = find_input_device()
            native_rate = _device_native_rate(device)
            print(f"[wake] mic device={device} rate={native_rate}")
        except Exception as exc:
            print(f"[wake] device error: {exc}")
            return
        chunk = 1024
        max_chunks   = int(2.0  * native_rate / chunk)
        silence_stop = int(0.5  * native_rate / chunk)
        min_chunks   = int(0.25 * native_rate / chunk)
        # Low threshold — Whisper rejects false triggers, so we'd rather not miss speech
        speech_threshold = max(0.005, ENERGY_THRESHOLD * 0.5)
        log_every = int(3.0 * native_rate / chunk)  # print RMS every ~3s

        while not stop_event.is_set():
            frames = []
            silent = 0
            started = False
            log_counter = 0

            try:
                stream_ctx = sd.RawInputStream(
                    samplerate=native_rate, channels=1, dtype="int16",
                    device=device, blocksize=chunk,
                )
            except Exception as exc:
                print(f"[wake] failed to open mic stream: {exc}")
                return

            with stream_ctx as stream:
                print("[wake] mic stream open, listening...")
                while not stop_event.is_set():
                    data, _ = stream.read(chunk)
                    arr = np.frombuffer(bytes(data), dtype=np.int16)
                    rms = np.sqrt(np.mean((arr.astype(np.float32) / 32768.0) ** 2))

                    log_counter += 1
                    if log_counter >= log_every:
                        print(f"[wake] listening — RMS {rms:.4f} (threshold {speech_threshold:.4f})")
                        log_counter = 0

                    if rms > speech_threshold:
                        started = True
                        silent = 0
                        frames.append(arr.copy())
                    elif started:
                        frames.append(arr.copy())
                        silent += 1
                        if silent >= silence_stop or len(frames) >= max_chunks:
                            break

            if stop_event.is_set() or len(frames) < min_chunks:
                continue

            raw = np.concatenate(frames).astype(np.float32) / 32768.0
            audio_16k = _resample(raw, native_rate, WHISPER_RATE)

            fd, wav_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            sf.write(wav_path, audio_16k, WHISPER_RATE, subtype="PCM_16")
            text = stt.transcribe(wav_path).lower()
            os.unlink(wav_path)
            print(f"[wake] heard: '{text}' (looking for '{WHISPER_KEYWORD}')")

            if WHISPER_KEYWORD.lower() in text:
                on_detected()
                return  # stream already closed

            # Brief cooldown so we don't hammer Whisper on ambient speech
            import time
            time.sleep(0.5)

    def _listen_porcupine(self, on_detected, stop_event):
        import sounddevice as sd
        from audio import find_input_device, _device_native_rate, _resample

        device = find_input_device()
        native_rate = _device_native_rate(device)
        target_rate = self._handle.sample_rate
        frame_len   = self._handle.frame_length
        native_chunk = max(256, int(frame_len * native_rate / target_rate))
        detected = False

        with sd.RawInputStream(
            samplerate=native_rate, channels=1, dtype="int16",
            device=device, blocksize=native_chunk,
        ) as stream:
            while not stop_event.is_set():
                data, _ = stream.read(native_chunk)
                audio = np.frombuffer(bytes(data), dtype=np.int16)
                audio_16k = _resample(audio.astype(np.float32) / 32768.0, native_rate, target_rate)
                frame = (audio_16k[:frame_len] * 32767).astype(np.int16)
                if len(frame) >= frame_len and self._handle.process(frame) >= 0:
                    detected = True
                    break

        if detected and not stop_event.is_set():
            on_detected()

    def _listen_oww(self, on_detected, stop_event):
        import sounddevice as sd
        from audio import find_input_device, _device_native_rate, _resample, WHISPER_RATE

        device = find_input_device()
        native_rate = _device_native_rate(device)
        chunk = max(256, int(0.08 * native_rate))
        detected = False

        with sd.RawInputStream(
            samplerate=native_rate, channels=1, dtype="int16",
            device=device, blocksize=chunk,
        ) as stream:
            while not stop_event.is_set():
                data, _ = stream.read(chunk)
                audio = np.frombuffer(bytes(data), dtype=np.int16)
                audio_16k = _resample(audio.astype(np.float32) / 32768.0, native_rate, WHISPER_RATE)
                scores = self._handle.predict((audio_16k * 32767).astype(np.int16))
                if scores.get(WAKE_WORD_MODEL, 0.0) >= WAKE_THRESHOLD:
                    self._handle.reset()
                    detected = True
                    break

        if detected and not stop_event.is_set():
            on_detected()
