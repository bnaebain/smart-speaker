"""
Smart Speaker — main entry point.

State machine:
  IDLE  ──(hold A)──►  LISTENING  ──(release A)──►  PROCESSING  ──►  SPEAKING  ──►  IDLE
                              └──(press B)──────────────────────────────────────►  IDLE

Hardware:
  Pimoroni Pirate Audio 3W Stereo Amp on RPi 4
  USB microphone for input
  GPIO 5  (A) — push-to-talk
  GPIO 6  (B) — cancel
  GPIO 16 (X) — volume up
  GPIO 24 (Y) — volume down
  GPIO 25     — DAC enable (must stay HIGH)
"""

import os
import signal
import sys
import tempfile
import threading
from enum import Enum, auto

import audio
import stt
import tts
from claude_client import ClaudeClient
from config import BTN_A, BTN_B, BTN_X, BTN_Y, DAC_ENABLE
from display_manager import DisplayManager

try:
    from gpiozero import Button, DigitalOutputDevice
    _GPIO_AVAILABLE = True
except (ImportError, Exception):
    _GPIO_AVAILABLE = False
    print("[main] gpiozero not available — running in keyboard-demo mode")


# ---------------------------------------------------------------------------
class State(Enum):
    IDLE       = auto()
    LISTENING  = auto()
    PROCESSING = auto()
    SPEAKING   = auto()


class SmartSpeaker:
    def __init__(self):
        self.state = State.IDLE
        self._state_lock = threading.Lock()
        self._stop_recording = threading.Event()
        self._cancel = threading.Event()
        self._worker: threading.Thread | None = None

        self.display = DisplayManager()
        self.claude = ClaudeClient()

        if _GPIO_AVAILABLE:
            self._dac = DigitalOutputDevice(DAC_ENABLE)
            self._dac.on()

            self._btn_a = Button(BTN_A, pull_up=True, bounce_time=0.05)
            self._btn_b = Button(BTN_B, pull_up=True, bounce_time=0.05)
            self._btn_x = Button(BTN_X, pull_up=True, bounce_time=0.05)
            self._btn_y = Button(BTN_Y, pull_up=True, bounce_time=0.05)

            self._btn_a.when_pressed  = self._on_a_pressed
            self._btn_a.when_released = self._on_a_released
            self._btn_b.when_pressed  = self._on_b_pressed
            self._btn_x.when_pressed  = self._on_vol_up
            self._btn_y.when_pressed  = self._on_vol_down

        self._volume = 80  # 0–100

    # ------------------------------------------------------------------
    # Button callbacks (called from gpiozero background thread)
    # ------------------------------------------------------------------

    def _on_a_pressed(self):
        with self._state_lock:
            if self.state == State.IDLE:
                self._transition(State.LISTENING)

    def _on_a_released(self):
        with self._state_lock:
            if self.state == State.LISTENING:
                self._stop_recording.set()

    def _on_b_pressed(self):
        with self._state_lock:
            if self.state != State.IDLE:
                print("[main] Cancelled")
                self._cancel.set()
                self._stop_recording.set()

    def _on_vol_up(self):
        self._volume = min(100, self._volume + 10)
        self._set_volume(self._volume)

    def _on_vol_down(self):
        self._volume = max(0, self._volume - 10)
        self._set_volume(self._volume)

    @staticmethod
    def _set_volume(vol: int):
        os.system(f"amixer -q sset Master {vol}%")

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def _transition(self, new_state: State):
        """Must be called with _state_lock held."""
        self.state = new_state
        print(f"[main] → {new_state.name}")

        if new_state == State.IDLE:
            self.display.show_idle()

        elif new_state == State.LISTENING:
            self._cancel.clear()
            self._stop_recording.clear()
            self.display.show_listening()
            self._worker = threading.Thread(target=self._run_pipeline, daemon=True)
            self._worker.start()

        elif new_state == State.PROCESSING:
            self.display.show_processing()

        elif new_state == State.SPEAKING:
            pass  # display updated in pipeline with response text

    # ------------------------------------------------------------------
    # Pipeline (runs in background thread)
    # ------------------------------------------------------------------

    def _run_pipeline(self):
        # 1. Record
        raw_audio = audio.record_until_stop(self._stop_recording)

        if self._cancel.is_set() or raw_audio is None or len(raw_audio) < SAMPLE_RATE * 0.3:
            with self._state_lock:
                self._transition(State.IDLE)
            return

        # 2. STT
        with self._state_lock:
            self._transition(State.PROCESSING)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name
        audio.save_wav(raw_audio, wav_path)
        text = stt.transcribe(wav_path)
        os.unlink(wav_path)

        if self._cancel.is_set() or not text:
            with self._state_lock:
                self._transition(State.IDLE)
            return

        # 3. Claude
        try:
            response = self.claude.chat(text)
        except Exception as exc:
            print(f"[main] Claude error: {exc}")
            self.display.show_error("Claude error")
            import time; time.sleep(2)
            with self._state_lock:
                self._transition(State.IDLE)
            return

        if self._cancel.is_set():
            with self._state_lock:
                self._transition(State.IDLE)
            return

        # 4. TTS + playback
        with self._state_lock:
            self.state = State.SPEAKING
        self.display.show_speaking(response)

        try:
            mp3_path = tts.synthesise(response)
            audio.play_mp3(mp3_path, cancel_event=self._cancel)
            os.unlink(mp3_path)
        except Exception as exc:
            print(f"[main] TTS/playback error: {exc}")

        with self._state_lock:
            self._transition(State.IDLE)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def run(self):
        print("[main] Smart Speaker starting …")
        with self._state_lock:
            self._transition(State.IDLE)

        if _GPIO_AVAILABLE:
            print("[main] Ready — hold button A to speak, B to cancel")
            signal.pause()
        else:
            # Keyboard fallback for development/testing
            print("[main] No GPIO — press ENTER to toggle recording, q to quit")
            while True:
                try:
                    key = input()
                except EOFError:
                    break
                if key.strip().lower() == "q":
                    break
                with self._state_lock:
                    if self.state == State.IDLE:
                        self._transition(State.LISTENING)
                    elif self.state == State.LISTENING:
                        self._stop_recording.set()

    def shutdown(self):
        self._cancel.set()
        self._stop_recording.set()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=5)
        print("[main] Shutdown complete")


# ---------------------------------------------------------------------------

from config import SAMPLE_RATE  # noqa: E402 (needed in pipeline)


def main():
    speaker = SmartSpeaker()

    def _sigterm(signum, frame):
        speaker.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _sigterm)
    signal.signal(signal.SIGINT, _sigterm)

    speaker.run()


if __name__ == "__main__":
    main()
