"""
Claude API client with rolling conversation history and tool use
for real-time weather and datetime.
"""

import weather as _weather
from anthropic import Anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, SYSTEM_PROMPT, MAX_HISTORY_TURNS

_TOOLS = [
    {
        "name": "get_weather",
        "description": (
            "Get current weather conditions for the user's location. "
            "Use whenever the user asks about weather, temperature, or outdoor conditions."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_datetime",
        "description": "Get the current date and time. Use when the user asks what time or day it is.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


def _run_tool(name: str) -> str:
    if name == "get_weather":
        lat, lon, city = _weather.get_location()
        if lat is None:
            return "Unable to determine location."
        return _weather.get_weather(lat, lon, city)
    if name == "get_datetime":
        return _weather.get_datetime()
    return "Unknown tool."


class ClaudeClient:
    def __init__(self):
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set")
        self._client = Anthropic(api_key=ANTHROPIC_API_KEY)
        self._history: list[dict] = []

    def chat(self, user_text: str) -> str:
        """Send a user message and return the assistant's spoken reply."""
        self._history.append({"role": "user", "content": user_text})

        max_msgs = MAX_HISTORY_TURNS * 2
        if len(self._history) > max_msgs:
            self._history = self._history[-max_msgs:]

        while True:
            response = self._client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=512,
                system=SYSTEM_PROMPT,
                messages=self._history,
                tools=_TOOLS,
            )

            if response.stop_reason == "tool_use":
                # Append assistant's tool-use turn, then inject results
                self._history.append({"role": "assistant", "content": response.content})
                results = [
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": _run_tool(block.name),
                    }
                    for block in response.content
                    if block.type == "tool_use"
                ]
                self._history.append({"role": "user", "content": results})
            else:
                reply = next(
                    (b.text for b in response.content if hasattr(b, "text")), ""
                ).strip()
                self._history.append({"role": "assistant", "content": reply})
                print(f"[claude] {reply}")
                return reply

    def reset(self):
        self._history.clear()
        print("[claude] History cleared")
