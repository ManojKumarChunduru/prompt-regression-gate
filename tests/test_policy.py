"""The policy file: declared inputs with reasons, and what a bad one does."""

from __future__ import annotations

import json

import pytest

from prg.exit_codes import PrgError
from prg.policy import DEFAULT_POLICY, Policy, load_policy

from .conftest import FIXTURE


def test_every_default_has_a_value_and_a_reason():
    assert all({"value", "reason"} <= set(v) for v in DEFAULT_POLICY.values())


def test_the_fixture_policy_matches_the_defaults_in_value_and_names_its_source():
    p = load_policy(FIXTURE / "policy" / "gate-policy.json")
    d = load_policy(None)
    assert (p.alpha, p.power, p.reviewed_set, p.draws_count, p.draws_size) == (
        d.alpha,
        d.power,
        d.reviewed_set,
        d.draws_count,
        d.draws_size,
    )
    assert p.source.endswith("gate-policy.json") and d.source == "built-in defaults"


def test_the_policy_lines_carry_every_input_with_a_reason():
    lines = load_policy(None).lines()
    assert len(lines) == 10 and all("(" in line and ")" in line for line in lines)
    assert lines[0].startswith("alpha = 0.05")


def _write(tmp_path, payload):
    p = tmp_path / "p.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_a_partial_policy_overrides_only_what_it_names(tmp_path):
    p = load_policy(_write(tmp_path, {"alpha": {"value": 0.01, "reason": "stricter"}}))
    assert p.alpha == 0.01 and p.power == 0.8 and p.reasons["alpha"] == "stricter"


def test_an_unknown_key_a_missing_reason_and_a_bad_range_are_refused(tmp_path):
    with pytest.raises(PrgError, match="unknown policy key 'beta'"):
        load_policy(_write(tmp_path, {"beta": {"value": 1, "reason": "r"}}))
    with pytest.raises(PrgError, match="needs a value and a reason"):
        load_policy(_write(tmp_path, {"alpha": {"value": 0.1}}))
    with pytest.raises(PrgError, match="strictly between 0 and 1"):
        load_policy(_write(tmp_path, {"alpha": {"value": 1.5, "reason": "r"}}))
    with pytest.raises(PrgError, match="must be first30 or all"):
        load_policy(_write(tmp_path, {"reviewed_set": {"value": "some", "reason": "r"}}))


def test_a_missing_invalid_or_non_object_policy_file_is_refused(tmp_path):
    with pytest.raises(PrgError, match="policy file not found"):
        load_policy(tmp_path / "nope.json")
    p = tmp_path / "bad.json"
    p.write_text("[", encoding="utf-8")
    with pytest.raises(PrgError, match="not valid JSON"):
        load_policy(p)
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(PrgError, match="must be a JSON object"):
        load_policy(p)


def test_a_policy_can_be_built_from_a_dictionary_directly():
    p = Policy.from_dict({"score_range": {"value": [0, 10], "reason": "ten-point scale"}}, "inline")
    assert (p.score_min, p.score_max, p.source) == (0, 10, "inline")
