#!/usr/bin/env python3
"""Test TTS synthesis and audio playback through the Pirate Audio amp."""
import asyncio
import os
import subprocess
import sys
import tempfile

import edge_tts

VOICE = "en-US-AriaNeural"
TEXT = "Hello! I am your smart speaker powered by Claude. If you can hear this, the speaker is working correctly."


async def synthesise(text, path):
    await edge_tts.Communicate(text, VOICE).save(path)


def main():
    print("Generating speech with edge-tts...")
    fd, mp3_path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)

    asyncio.run(synthesise(TEXT, mp3_path))
    print(f"Playing via mpg123: {mp3_path}")

    result = subprocess.run(["mpg123", mp3_path], capture_output=True, text=True)
    os.unlink(mp3_path)

    if result.returncode != 0:
        print(f"mpg123 error:\n{result.stderr}")
        sys.exit(1)
    else:
        print("Done. Did you hear it?")


if __name__ == "__main__":
    main()
