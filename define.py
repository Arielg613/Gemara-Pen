import os
import re

import anthropic

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set.")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def get_contextual_definition(word: str, aramaic: str, english: str) -> str:
    """Ask Claude what a word means in the context of a specific Talmud passage."""
    clean_aramaic = re.sub(r"<[^>]+>", "", aramaic).strip()

    message = _get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=120,
        messages=[{
            "role": "user",
            "content": (
                f"You are an expert in Talmudic Aramaic and Hebrew.\n\n"
                f"A student is studying Gemara and encountered the word \"{word}\".\n\n"
                f"Passage (Aramaic): {clean_aramaic}\n\n"
                f"Passage (English translation): {english}\n\n"
                f"In 1–2 sentences, explain what \"{word}\" means specifically in this passage. "
                f"Be direct and plain — no preamble like 'In this context'."
            ),
        }],
    )
    return message.content[0].text.strip()
