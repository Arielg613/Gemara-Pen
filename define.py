import os
import re

import google.generativeai as genai

_model = None


def _get_model():
    global _model
    if _model is None:
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY environment variable is not set.")
        genai.configure(api_key=api_key)
        _model = genai.GenerativeModel("gemini-1.5-flash")
    return _model


def get_contextual_definition(word: str, aramaic: str, english: str) -> str:
    """Ask Gemini what a word means in the context of a specific Talmud passage."""
    clean_aramaic = re.sub(r"<[^>]+>", "", aramaic).strip()

    prompt = (
        f"You are an expert in Talmudic Aramaic and Hebrew.\n\n"
        f"A student is studying Gemara and encountered the word \"{word}\".\n\n"
        f"Passage (Aramaic): {clean_aramaic}\n\n"
        f"Passage (English translation): {english}\n\n"
        f"In 1–2 sentences, explain what \"{word}\" means specifically in this passage. "
        f"Be direct and plain — no preamble like 'In this context'."
    )

    response = _get_model().generate_content(prompt)
    return response.text.strip()
