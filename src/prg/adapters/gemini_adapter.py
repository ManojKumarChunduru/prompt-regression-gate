"""The Gemini adapter: the live path, never on the default path and never in CI.

Needs GEMINI_API_KEY in the environment and the `gemini` extra installed. Same file shape, same
caveat as the OpenAI adapter: no number in this repository comes from here (ADR-005).
"""

from __future__ import annotations

import os

from ..exit_codes import PrgError

NAME = "gemini"
DEFAULT_MODEL = "gemini-2.0-flash"


def generate(prompt: str, model: str | None = None) -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise PrgError("the gemini adapter needs GEMINI_API_KEY in the environment")
    try:
        from google import genai
    except ImportError as exc:
        raise PrgError("the gemini adapter needs the gemini extra: pip install 'prompt-regression-gate[gemini]'") from exc
    client = genai.Client(api_key=key)
    response = client.models.generate_content(model=model or DEFAULT_MODEL, contents=prompt)
    return (response.text or "").strip()
