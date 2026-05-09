"""
Claude API client with rolling conversation history.
"""

from anthropic import Anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, SYSTEM_PROMPT, MAX_HISTORY_TURNS


class ClaudeClient:
    def __init__(self):
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set")
        self._client = Anthropic(api_key=ANTHROPIC_API_KEY)
        self._history: list[dict] = []

    def chat(self, user_text: str) -> str:
        """Send a user message and return the assistant reply."""
        self._history.append({"role": "user", "content": user_text})

        # Keep history within token budget
        max_msgs = MAX_HISTORY_TURNS * 2
        if len(self._history) > max_msgs:
            self._history = self._history[-max_msgs:]

        response = self._client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=self._history,
        )
        reply = response.content[0].text.strip()
        self._history.append({"role": "assistant", "content": reply})
        print(f"[claude] {reply}")
        return reply

    def reset(self):
        """Clear conversation history."""
        self._history.clear()
        print("[claude] History cleared")
