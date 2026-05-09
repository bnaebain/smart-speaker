"""
ST7789 display driver wrapper for Pirate Audio 3W Stereo Amp.

Pirate Audio pinout:
  SPI0 CE1 (BCM 7) — chip select
  GPIO 9            — data/command
  GPIO 13           — backlight
  240x240 IPS, ST7789 controller
"""

import textwrap
from config import (
    DISPLAY_WIDTH, DISPLAY_HEIGHT,
    COL_BG, COL_ACCENT, COL_WHITE, COL_DIM,
    COL_LISTEN, COL_THINK, COL_SPEAK,
)

try:
    import st7789 as ST7789
    from PIL import Image, ImageDraw, ImageFont
    _HW_AVAILABLE = True
except ImportError:
    _HW_AVAILABLE = False

_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _load_font(size, bold=False):
    try:
        path = _FONT_BOLD_PATH if bold else _FONT_PATH
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


class DisplayManager:
    def __init__(self):
        if not _HW_AVAILABLE:
            print("[display] ST7789 / Pillow not available — running headless")
            self._display = None
            return

        self._display = ST7789.ST7789(
            height=DISPLAY_HEIGHT,
            rotation=90,
            port=0,
            cs=ST7789.BG_SPI_CS_FRONT,  # CE1
            dc=9,
            backlight=13,
            spi_speed_hz=80_000_000,
            offset_left=0,
            offset_top=0,
        )
        self._display.begin()

        self._font_large = _load_font(28, bold=True)
        self._font_med   = _load_font(20)
        self._font_small = _load_font(16)

    # ------------------------------------------------------------------
    def _push(self, img):
        if self._display:
            self._display.display(img)

    def _blank(self):
        img = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), COL_BG)
        draw = ImageDraw.Draw(img)
        return img, draw

    def _centered_text(self, draw, text, y, font, colour):
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        draw.text(((DISPLAY_WIDTH - w) // 2, y), text, font=font, fill=colour)

    # ------------------------------------------------------------------
    def show_idle(self):
        img, draw = self._blank()
        # Simple speaker icon (circle + lines)
        cx, cy, r = 120, 90, 28
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=COL_ACCENT, width=3)
        draw.ellipse((cx - 10, cy - 10, cx + 10, cy + 10), fill=COL_ACCENT)
        for dr, alpha in [(38, 180), (50, 140), (62, 100)]:
            draw.arc((cx - dr, cy - dr, cx + dr, cy + dr),
                     start=210, end=330, fill=(*COL_ACCENT, alpha), width=2)

        self._centered_text(draw, "Smart Speaker", 135, self._font_large, COL_WHITE)
        self._centered_text(draw, "Say 'Hey Jarvis'", 168, self._font_small, COL_DIM)
        self._centered_text(draw, "or hold button  A", 188, self._font_small, COL_DIM)
        self._push(img)

    def show_listening(self):
        img, draw = self._blank()
        # Pulsing mic circle
        cx, cy = 120, 95
        draw.ellipse((cx - 40, cy - 40, cx + 40, cy + 40),
                     fill=COL_LISTEN, outline=(255, 120, 120), width=3)
        # Mic body
        draw.rounded_rectangle((cx - 10, cy - 28, cx + 10, cy + 10),
                                radius=8, fill=COL_BG)
        draw.arc((cx - 18, cy - 2, cx + 18, cy + 26),
                 start=0, end=180, fill=COL_BG, width=3)
        draw.line((cx, cy + 26, cx, cy + 36), fill=COL_BG, width=3)

        self._centered_text(draw, "Listening...", 152, self._font_large, COL_LISTEN)
        self._centered_text(draw, "Release A to send  •  B to cancel",
                            190, self._font_small, COL_DIM)
        self._push(img)

    def show_processing(self):
        img, draw = self._blank()
        # Spinning dots (static — just show three dots)
        cx, cy = 120, 95
        for i, angle_deg in enumerate([210, 270, 330]):
            import math
            angle = math.radians(angle_deg)
            x = cx + int(36 * math.cos(angle))
            y = cy + int(36 * math.sin(angle))
            radius = 10 - i * 2
            draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                         fill=COL_THINK)

        self._centered_text(draw, "Thinking...", 152, self._font_large, COL_THINK)
        self._centered_text(draw, "B to cancel", 190, self._font_small, COL_DIM)
        self._push(img)

    def show_speaking(self, text: str):
        img, draw = self._blank()
        # Wrap text to fit display
        lines = textwrap.wrap(text, width=22)[:6]  # max 6 lines
        y = 10
        for line in lines:
            draw.text((10, y), line, font=self._font_small, fill=COL_WHITE)
            y += 22

        self._centered_text(draw, "Speaking", DISPLAY_HEIGHT - 40,
                            self._font_med, COL_SPEAK)
        self._push(img)

    def show_error(self, message: str = "Error"):
        img, draw = self._blank()
        self._centered_text(draw, "!", 70, self._font_large, (220, 60, 60))
        self._centered_text(draw, message, 130, self._font_med, (220, 100, 100))
        self._centered_text(draw, "Press A to retry", 170, self._font_small, COL_DIM)
        self._push(img)
