"""The declared grammar: sentences, atoms, vocabularies, roles, and what a bad grammar file does."""

from __future__ import annotations

import json

import pytest

from prg.claims import extract_atoms, load_grammar, plays_role, split_sentences
from prg.exit_codes import PrgError

from .helpers import GRAMMAR

VOCAB = {"Product__c": ["Aero 2", "Pulse Band"], "Contact.Name": ["Priya Natarajan"]}


@pytest.fixture(scope="module")
def grammar():
    return load_grammar(GRAMMAR)


def test_the_grammar_declares_nine_atom_kinds_each_with_a_reason(grammar):
    assert [r.kind for r in grammar.rules] == [
        "money",
        "date",
        "duration",
        "identifier",
        "priority",
        "status",
        "product",
        "contact",
        "action",
    ]
    assert all(r.reason for r in grammar.rules)
    assert grammar.verdict_order == ["contradicted", "misgrounded", "unsupported", "supported", "unverifiable"]


def test_sentences_split_on_terminal_punctuation_followed_by_a_capital_or_a_dollar(grammar):
    text = "Priya reported it since 2026-02-01. The agent offered a refund of $240.00. $10 was waived! Really? Yes."
    assert split_sentences(text, grammar) == [
        "Priya reported it since 2026-02-01.",
        "The agent offered a refund of $240.00.",
        "$10 was waived!",
        "Really?",
        "Yes.",
    ]


def test_a_decimal_amount_does_not_split_a_sentence(grammar):
    assert len(split_sentences("The refund of $240.00 cleared.", grammar)) == 1


def test_atoms_come_out_in_order_of_appearance_with_their_kind(grammar):
    atoms = extract_atoms("Priya Natarajan said the Aero 2 was bought for $240.00 on 2026-02-01 under ORD-77001.", grammar, VOCAB)
    assert [(a.kind, a.value) for a in atoms] == [
        ("contact", "Priya Natarajan"),
        ("product", "Aero 2"),
        ("money", "$240.00"),
        ("date", "2026-02-01"),
        ("identifier", "ORD-77001"),
    ]


def test_a_span_claimed_by_one_rule_is_not_claimed_by_another(grammar):
    # "24-month" is a duration; the "24" inside it must not become anything else, and the date inside
    # an identifier-free sentence is one atom.
    atoms = extract_atoms("Units carry a 24-month warranty from 2026-02-01.", grammar, VOCAB)
    assert [(a.kind, a.value) for a in atoms] == [("duration", "24-month"), ("date", "2026-02-01")]


def test_priority_and_status_words_are_case_sensitive_whole_words(grammar):
    atoms = extract_atoms("The case is High priority and the status is New; the newest highlight is closed.", grammar, VOCAB)
    assert [(a.kind, a.value) for a in atoms] == [("priority", "High"), ("status", "New")]


def test_actions_are_case_insensitive_whole_words(grammar):
    atoms = extract_atoms("A Refund and a replacement were offered, not refunds.", grammar, VOCAB)
    assert [(a.kind, a.value) for a in atoms] == [("action", "Refund"), ("action", "replacement")]


def test_a_vocabulary_drawn_from_the_export_matches_only_known_names(grammar):
    atoms = extract_atoms("Priya Natarajan and Someone Else own an Aero 2 and a Zeta 9.", grammar, VOCAB)
    assert [(a.kind, a.value) for a in atoms] == [("contact", "Priya Natarajan"), ("product", "Aero 2")]


def test_an_empty_vocabulary_matches_nothing(grammar):
    assert extract_atoms("Priya Natarajan owns an Aero 2.", grammar, {}) == []


def test_a_sentence_with_no_atom_yields_no_atoms(grammar):
    assert extract_atoms("The customer sounds frustrated and wants a quick resolution.", grammar, VOCAB) == []


def test_a_role_is_played_when_a_keyword_is_present_or_the_rule_has_none(grammar):
    assert plays_role("The agent offered a refund of $240.00.", grammar.rule("money")) is True
    assert plays_role("$240.00 is the price.", grammar.rule("money")) is False
    assert plays_role("Anything at all.", grammar.rule("product")) is True
    assert plays_role("Anything at all.", grammar.rule("date")) is False


def test_the_grammar_accessor_refuses_an_unknown_kind(grammar):
    with pytest.raises(PrgError, match="no atom kind 'colour'"):
        grammar.rule("colour")


def _write(tmp_path, payload):
    p = tmp_path / "g.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_a_missing_or_invalid_grammar_file_is_refused(tmp_path):
    with pytest.raises(PrgError, match="grammar file not found"):
        load_grammar(tmp_path / "nope.json")
    p = tmp_path / "bad.json"
    p.write_text("{", encoding="utf-8")
    with pytest.raises(PrgError, match="not valid JSON"):
        load_grammar(p)


def test_a_grammar_without_a_sentence_pattern_or_with_a_bad_one_is_refused(tmp_path):
    with pytest.raises(PrgError, match="sentence_split"):
        load_grammar(_write(tmp_path, {"atoms": {"x": {"pattern": "a", "reason": "r"}}}))
    with pytest.raises(PrgError, match="sentence_split"):
        load_grammar(_write(tmp_path, {"sentence_split": {"pattern": "("}, "atoms": {"x": {"pattern": "a", "reason": "r"}}}))


def test_an_atom_without_a_reason_or_without_a_matcher_is_refused(tmp_path):
    base = {"sentence_split": {"pattern": r"\. "}}
    with pytest.raises(PrgError, match="has no reason"):
        load_grammar(_write(tmp_path, {**base, "atoms": {"x": {"pattern": "a"}}}))
    with pytest.raises(PrgError, match="needs a pattern"):
        load_grammar(_write(tmp_path, {**base, "atoms": {"x": {"reason": "r"}}}))
    with pytest.raises(PrgError, match="pattern is invalid"):
        load_grammar(_write(tmp_path, {**base, "atoms": {"x": {"pattern": "(", "reason": "r"}}}))


def test_a_grammar_with_no_atoms_is_refused(tmp_path):
    with pytest.raises(PrgError, match="no atoms"):
        load_grammar(_write(tmp_path, {"sentence_split": {"pattern": r"\. "}, "atoms": {}}))


def test_the_verdict_order_defaults_when_absent(tmp_path):
    g = load_grammar(_write(tmp_path, {"sentence_split": {"pattern": r"\. "}, "atoms": {"x": {"pattern": "a", "reason": "r"}}}))
    assert g.verdict_order[0] == "contradicted" and g.verdict_order[-1] == "unverifiable"
