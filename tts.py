"""
Text-to-speech using edge-tts (Microsoft Edge neural voices, free, online).

Synthesises to a temp MP3 file which the caller plays via audio.play_mp3().
"""

import asyncio
import tempfile
import os
import edge_tts
from config import TTS_VOICE


async def _synthesise(text: str, out_path: str) -> None:
    communicate = edge_tts.Communicate(text, TTS_VOICE)
    await communicate.save(out_path)


def synthesise(text: str) -> str:
    """
    Convert text to speech and return path to the MP3 temp file.
    Caller is responsible for deleting the file after playback.
    """
    fd, path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    asyncio.run(_synthesise(text, path))
    return path
