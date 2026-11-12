"""The OpenAI adapter: the live path, never on the default path and never in CI.

Needs OPENAI_API_KEY in the environment and the `openai` extra installed. Writes the same file
shape the fixture adapter writes, so the gate reads one shape. No number in this repository comes
from this module (ADR-005); it exists so the README's "run it against a real model" instruction
is one flag away, with the key as the only difference.
"""

from __future__ import annotations

import os

from ..exit_codes import PrgError

NAME = "openai"
DEFAULT_MODEL = "gpt-4o-mini"


def generate(prompt: str, model: str | None = None) -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise PrgError("the openai adapter needs OPENAI_API_KEY in the environment")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise PrgError("the openai adapter needs the openai extra: pip install 'prompt-regression-gate[openai]'") from exc
    client = OpenAI(api_key=key)
    response = client.chat.completions.create(
        model=model or DEFAULT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return (response.choices[0].message.content or "").strip()
