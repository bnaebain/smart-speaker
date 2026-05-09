import os

# --- Claude ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"
MAX_HISTORY_TURNS = 10
SYSTEM_PROMPT = (
    "You are a smart speaker assistant. Give concise, natural spoken responses. "
    "Never use markdown, bullet points, numbered lists, or formatting symbols. "
    "Keep answers under 3 sentences unless the user explicitly asks for more detail."
)

# --- GPIO (BCM numbering) ---
BTN_A = 5    # Push-to-talk
BTN_B = 6    # Cancel
BTN_X = 16   # Volume up
BTN_Y = 24   # Volume down
DAC_ENABLE = 25  # Must be HIGH for Pirate Audio amp to work

# --- Audio ---
SAMPLE_RATE = 16000
CHANNELS = 1
MAX_RECORD_SECONDS = 60
# Substring matched against ALSA device names to find USB mic
USB_MIC_KEYWORD = "USB"

# --- STT ---
WHISPER_MODEL = "tiny.en"  # ~75 MB; upgrade to "base.en" for better accuracy

# --- TTS ---
TTS_VOICE = "en-US-ChristopherNeural"

# --- Wake word ---
# Picovoice Porcupine (custom "Nova" wake word — recommended)
PORCUPINE_ACCESS_KEY = os.environ.get("PORCUPINE_ACCESS_KEY", "")
PORCUPINE_MODEL_PATH = "nova_raspberry-pi.ppn"  # place in smart-speaker dir

# openwakeword fallback (used when Porcupine is not configured)
WAKE_WORD_MODEL  = "hey_jarvis"
WAKE_THRESHOLD   = 0.5

SILENCE_TIMEOUT   = 1.5           # seconds of silence before VAD stops recording
SPEECH_THRESHOLD  = 0.03          # RMS above this = someone is speaking
SILENCE_THRESHOLD = 0.01          # RMS below this = silence (lower than speech)
ENERGY_THRESHOLD  = 0.005         # wake word mic sensitivity (kept low)

# --- Display ---
DISPLAY_WIDTH = 240
DISPLAY_HEIGHT = 240
# Colours (R, G, B)
COL_BG        = (15, 15, 35)
COL_ACCENT    = (100, 149, 237)   # cornflower blue
COL_WHITE     = (220, 220, 220)
COL_DIM       = (90, 90, 110)
COL_LISTEN    = (220, 80, 80)     # red while recording
COL_THINK     = (80, 180, 220)    # cyan while processing
COL_SPEAK     = (80, 220, 130)    # green while speaking
