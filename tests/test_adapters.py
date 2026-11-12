"""The adapter boundary: the default path imports nothing optional, and the live adapters need a key."""

from __future__ import annotations

import subprocess
import sys

import pytest

from prg.adapters import ADAPTERS, FORBIDDEN_ON_DEFAULT_PATH, load_adapter
from prg.exit_codes import PrgError

from .conftest import FIXTURE, ROOT


def test_the_registry_names_three_adapters_and_refuses_a_fourth():
    assert list(ADAPTERS) == ["fixture", "openai", "gemini"]
    with pytest.raises(PrgError, match="unknown adapter 'claude'"):
        load_adapter("claude")


def test_loading_the_fixture_adapter_in_a_fresh_interpreter_imports_no_optional_module():
    code = (
        "import sys\nfrom prg.adapters import load_adapter, FORBIDDEN_ON_DEFAULT_PATH\n"
        "assert load_adapter('fixture').NAME == 'fixture'\n"
        "print([m for m in FORBIDDEN_ON_DEFAULT_PATH if m in sys.modules])\n"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True, capture_output=True, text=True).stdout
    assert out.strip() == "[]"


def test_running_the_gate_in_a_fresh_interpreter_imports_none_of_the_forbidden_modules():
    code = (
        "import sys, prg.cli\n"
        f"prg.cli.main(['gate', '--project', r'{FIXTURE}', '--baseline', 'v1', '--candidate', 'v3', '--quiet'])\n"
        f"bad = [m for m in {list(FORBIDDEN_ON_DEFAULT_PATH)!r} if m in sys.modules]\n"
        "print(bad)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True, capture_output=True, text=True).stdout
    assert out.strip() == "[]"


def test_the_live_adapters_need_their_key_before_anything_else(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(PrgError, match="OPENAI_API_KEY"):
        load_adapter("openai").generate("prompt")
    with pytest.raises(PrgError, match="GEMINI_API_KEY"):
        load_adapter("gemini").generate("prompt")


def test_the_live_adapters_name_their_extra_when_the_client_library_is_missing(monkeypatch):
    import builtins

    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    real = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name in ("openai", "google", "google.genai") or name.startswith("google."):
            raise ImportError(f"no {name}")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)
    with pytest.raises(PrgError, match=r"\[openai\]"):
        load_adapter("openai").generate("prompt")
    with pytest.raises(PrgError, match=r"\[gemini\]"):
        load_adapter("gemini").generate("prompt")


def test_the_live_adapters_default_models_are_declared_strings():
    assert isinstance(load_adapter("openai").DEFAULT_MODEL, str)
    assert isinstance(load_adapter("gemini").DEFAULT_MODEL, str)
