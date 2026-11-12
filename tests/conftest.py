"""Shared fixtures: the committed fixture loaded once, the small corpus written per test."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prg.gate import load_context

from .helpers import paths, write_corpus

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "fixture"
FIXTURE_PATHS = {
    "project_dir": FIXTURE,
    "data_dir": FIXTURE / "data",
    "generations_dir": FIXTURE / "generations",
    "reviews_dir": FIXTURE / "reviews",
    "policy_path": FIXTURE / "policy" / "gate-policy.json",
    "grammar_path": FIXTURE / "policy" / "claim-grammar.json",
}


@pytest.fixture(scope="session")
def ctx():
    return load_context(**FIXTURE_PATHS)


@pytest.fixture(scope="session")
def truth():
    return json.loads((FIXTURE / "EXPECTED_VERDICTS.json").read_text(encoding="utf-8"))


@pytest.fixture
def mini(tmp_path):
    """The small corpus's project directory, fresh for every test."""
    return write_corpus(tmp_path)


@pytest.fixture
def mini_ctx(mini):
    return load_context(**paths(mini))


@pytest.fixture
def mini_paths(mini):
    return paths(mini)
