"""
Smart Speaker — main entry point.

Activation:
  • Say "Hey Jarvis"  — wake word (auto VAD stop)
  • Hold button A     — push-to-talk (release to stop)
  • Button B          — cancel at any stage

Display / buttons on Pimoroni Pirate Audio 3W Stereo Amp:
  BCM 5  (A) — PTT      BCM 6  (B) — cancel
  BCM 16 (X) — vol up   BCM 24 (Y) — vol down
  BCM 25     — DAC enable (must stay HIGH)
"""

import os
import signal
import sys
import tempfile
import threading
import time
from enum import Enum, auto

import audio
import stt
import tts
from claude_client import ClaudeClient
from config import BTN_A, BTN_B, BTN_X, BTN_Y, DAC_ENABLE
from display_manager import DisplayManager
from wake_word import WakeWordDetector

try:
    from gpiozero import Button, DigitalOutputDevice
    _GPIO = True
except Exception:
    _GPIO = False
    print("[main] gpiozero unavailable — keyboard fallback active")


class State(Enum):
    IDLE       = auto()
    RECORDING  = auto()
    PROCESSING = auto()
    SPEAKING   = auto()


class SmartSpeaker:
    def __init__(self):
        self.state = State.IDLE
        self._lock = threading.Lock()
        self._stop_rec = threading.Event()
        self._cancel   = threading.Event()
        self._wake_stop = threading.Event()
        self._ptt_mode  = False

        self.display  = DisplayManager()
        self.claude   = ClaudeClient()
        self.detector = WakeWordDetector()
        self._volume  = 80

        if _GPIO:
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

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def _on_a_pressed(self):
        with self._lock:
            if self.state == State.IDLE:
                self.state = State.RECORDING
                self._ptt_mode = True
                self._wake_stop.set()
                self._cancel.clear()
                self._stop_rec.clear()
                threading.Thread(target=self._pipeline, daemon=True).start()
            elif self.state == State.RECORDING and not self._ptt_mode:
                # Wake word mode — A pressed means "I'm done talking, submit now"
                self._stop_rec.set()

    def _on_a_released(self):
        if self._ptt_mode:
            self._stop_rec.set()

    def _on_b_pressed(self):
        self._cancel.set()
        self._stop_rec.set()
        self._wake_stop.set()

    def _on_vol_up(self):
        self._volume = min(100, self._volume + 10)
        os.system(f"amixer -q sset Master {self._volume}%")

    def _on_vol_down(self):
        self._volume = max(0, self._volume - 10)
        os.system(f"amixer -q sset Master {self._volume}%")

    # ------------------------------------------------------------------
    # Wake word
    # ------------------------------------------------------------------

    def _on_wake_word(self):
        """Called by WakeWordDetector AFTER its mic stream has closed."""
        with self._lock:
            if self.state != State.IDLE:
                return
            self.state = State.RECORDING
            self._ptt_mode = False
        self._cancel.clear()
        self._stop_rec.clear()
        threading.Thread(target=self._pipeline, daemon=True).start()

    def _start_wake_listener(self):
        if not self.detector.available:
            return
        self._wake_stop.clear()
        threading.Thread(
            target=self.detector.listen,
            args=(self._on_wake_word, self._wake_stop),
            daemon=True,
        ).start()

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def _pipeline(self):
        if self._ptt_mode:
            # Give wake listener stream up to 200ms to close
            time.sleep(0.2)

        audio.play_beep()
        self.display.show_listening()

        # 1. Record
        if self._ptt_mode:
            raw = audio.record_until_stop(self._stop_rec)
        else:
            raw = audio.record_with_vad(self._cancel, stop_early=self._stop_rec)

        if self._cancel.is_set() or raw is None or len(raw) < audio.WHISPER_RATE * 0.3:
            self._idle()
            return

        # 2. STT
        with self._lock:
            self.state = State.PROCESSING
        self.display.show_processing()

        fd, wav_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        audio.save_wav(raw, wav_path)
        text = stt.transcribe(wav_path)
        os.unlink(wav_path)

        if self._cancel.is_set() or not text:
            self._idle()
            return

        # 3. Claude (with tool use for weather/time)
        try:
            response = self.claude.chat(text)
        except Exception as exc:
            print(f"[main] Claude error: {exc}")
            self.display.show_error("Claude error")
            time.sleep(2)
            self._idle()
            return

        if self._cancel.is_set():
            self._idle()
            return

        # 4. TTS + playback
        with self._lock:
            self.state = State.SPEAKING
        self.display.show_speaking(response)

        try:
            mp3 = tts.synthesise(response)
            audio.play_mp3(mp3, cancel_event=self._cancel)
            os.unlink(mp3)
        except Exception as exc:
            print(f"[main] TTS error: {exc}")

        self._idle()

    def _idle(self):
        with self._lock:
            self.state = State.IDLE
        self.display.show_idle()
        self._start_wake_listener()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def run(self):
        print("[main] Smart Speaker starting …")
        self.display.show_idle()
        self._start_wake_listener()

        if self.detector.available:
            print("[main] Say 'Hey Jarvis' or hold button A to speak")
        else:
            print("[main] Hold button A to speak")

        if _GPIO:
            signal.pause()
        else:
            print("[main] Press ENTER to toggle PTT, q to quit")
            while True:
                try:
                    key = input()
                except EOFError:
                    break
                if key.strip().lower() == "q":
                    break
                with self._lock:
                    if self.state == State.IDLE:
                        self._on_a_pressed()
                    elif self.state == State.RECORDING:
                        self._stop_rec.set()

    def shutdown(self):
        self._cancel.set()
        self._wake_stop.set()
        self._stop_rec.set()
        print("[main] Shutdown complete")


# ---------------------------------------------------------------------------

def main():
    speaker = SmartSpeaker()

    def _sig(signum, frame):
        speaker.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)
    speaker.run()


if __name__ == "__main__":
    main()
