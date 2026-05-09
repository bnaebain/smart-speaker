#!/usr/bin/env python3
"""Run this directly to test the ST7789 display in isolation."""
import sys

try:
    import ST7789
except ImportError:
    sys.exit("ST7789 not installed — activate the venv first: source venv/bin/activate")

from PIL import Image, ImageDraw

print("Initialising display...")
try:
    display = ST7789.ST7789(
        height=240,
        rotation=90,
        port=0,
        cs=ST7789.BG_SPI_CS_FRONT,
        dc=9,
        backlight=13,
        spi_speed_hz=80_000_000,
    )
    display.begin()
    print("  OK — using BG_SPI_CS_FRONT")
except AttributeError:
    print("  BG_SPI_CS_FRONT not found, trying cs=1 directly...")
    display = ST7789.ST7789(
        height=240,
        rotation=90,
        port=0,
        cs=1,
        dc=9,
        backlight=13,
        spi_speed_hz=80_000_000,
    )
    display.begin()
    print("  OK — using cs=1")

print("Drawing solid blue screen...")
img = Image.new("RGB", (240, 240), (30, 80, 200))
draw = ImageDraw.Draw(img)
draw.text((60, 110), "IT WORKS!", fill=(255, 255, 255))
display.display(img)
print("Done — do you see a blue screen with IT WORKS! ?")
