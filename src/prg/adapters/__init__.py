"""The adapter registry: which module writes generations for a template version.

`fixture` is the seeded stand-in model and the only adapter the default path imports. `openai`
and `gemini` are imported inside their functions when named, need a key from the environment, and
produce no number in this repository (ADR-005). The registry maps names to import paths rather
than to modules so that importing this package imports none of them.
"""

from __future__ import annotations

import importlib

from ..exit_codes import PrgError

ADAPTERS = {
    "fixture": "prg.adapters.fixture",
    "openai": "prg.adapters.openai_adapter",
    "gemini": "prg.adapters.gemini_adapter",
}

FORBIDDEN_ON_DEFAULT_PATH = (
    "openai",
    "google",
    "google.genai",
    "fastapi",
    "uvicorn",
    "prg.adapters.openai_adapter",
    "prg.adapters.gemini_adapter",
)


def load_adapter(name: str):
    if name not in ADAPTERS:
        raise PrgError(f"unknown adapter {name!r}; adapters are {', '.join(ADAPTERS)}")
    return importlib.import_module(ADAPTERS[name])
