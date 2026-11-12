"""Splits a summary into claims and each claim into atoms, by a declared grammar.

The grammar is a JSON file with a reason per rule, because a grammar is a declared semantics and
not a measurement: the recall it achieves against the planted faults is measured, the rules
themselves are chosen. An atom is a checkable thing in a sentence: a dollar figure, a date, a
duration, an identifier, a picklist value, a product, a person, an action. A sentence with no atom
is unverifiable and is counted, never gated on.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .exit_codes import PrgError


@dataclass(frozen=True)
class Atom:
    kind: str
    value: str
    start: int


@dataclass
class AtomRule:
    kind: str
    pattern: re.Pattern | None
    vocabulary: list[str]
    vocabulary_from: str | None
    field_role: str | None
    role_keywords: list[str]
    case_insensitive: bool
    reason: str


@dataclass
class Grammar:
    source: str
    sentence_split: re.Pattern
    rules: list[AtomRule]
    verdict_order: list[str]
    reasons: dict[str, str] = field(default_factory=dict)

    def rule(self, kind: str) -> AtomRule:
        for r in self.rules:
            if r.kind == kind:
                return r
        raise PrgError(f"grammar has no atom kind {kind!r}")


def load_grammar(path: Path) -> Grammar:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PrgError(f"grammar file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PrgError(f"{path}: not valid JSON ({exc.msg} at line {exc.lineno})") from exc
    try:
        split = re.compile(raw["sentence_split"]["pattern"])
    except (KeyError, re.error) as exc:
        raise PrgError(f"{path}: sentence_split needs a valid pattern ({exc})") from exc
    rules: list[AtomRule] = []
    reasons: dict[str, str] = {"sentence_split": raw["sentence_split"].get("reason", "")}
    for kind, entry in raw.get("atoms", {}).items():
        if "reason" not in entry:
            raise PrgError(f"{path}: atom {kind!r} has no reason")
        if "pattern" not in entry and "vocabulary" not in entry and "vocabulary_from" not in entry:
            raise PrgError(f"{path}: atom {kind!r} needs a pattern, a vocabulary or a vocabulary_from")
        try:
            pattern = re.compile(entry["pattern"]) if "pattern" in entry else None
        except re.error as exc:
            raise PrgError(f"{path}: atom {kind!r} pattern is invalid ({exc})") from exc
        rules.append(
            AtomRule(
                kind=kind,
                pattern=pattern,
                vocabulary=list(entry.get("vocabulary", [])),
                vocabulary_from=entry.get("vocabulary_from"),
                field_role=entry.get("field_role"),
                role_keywords=list(entry.get("role_keywords", [])),
                case_insensitive=bool(entry.get("case_insensitive", False)),
                reason=entry["reason"],
            )
        )
        reasons[kind] = entry["reason"]
    if not rules:
        raise PrgError(f"{path}: no atoms")
    order = raw.get("verdict_order", ["contradicted", "misgrounded", "unsupported", "supported", "unverifiable"])
    return Grammar(source=str(path), sentence_split=split, rules=rules, verdict_order=order, reasons=reasons)


def split_sentences(text: str, grammar: Grammar) -> list[str]:
    parts = [p.strip() for p in grammar.sentence_split.split(text.strip()) if p.strip()]
    return parts


def _vocab_pattern(words: list[str], case_insensitive: bool) -> re.Pattern | None:
    if not words:
        return None
    escaped = sorted((re.escape(w) for w in words), key=len, reverse=True)
    return re.compile(r"(?<![\w-])(?:" + "|".join(escaped) + r")(?![\w-])", re.I if case_insensitive else 0)


def extract_atoms(sentence: str, grammar: Grammar, vocabularies: dict[str, list[str]]) -> list[Atom]:
    """Atoms in one sentence, in order of appearance; a span claimed by one rule is not claimed by another."""
    taken: list[tuple[int, int]] = []
    atoms: list[Atom] = []
    for rule in grammar.rules:
        pattern = rule.pattern
        if pattern is None:
            words = rule.vocabulary or vocabularies.get(rule.vocabulary_from or "", [])
            pattern = _vocab_pattern(words, rule.case_insensitive)
            if pattern is None:
                continue
        for match in pattern.finditer(sentence):
            span = (match.start(), match.end())
            if any(not (span[1] <= s or span[0] >= e) for s, e in taken):
                continue
            taken.append(span)
            atoms.append(Atom(rule.kind, match.group(0), match.start()))
    atoms.sort(key=lambda a: a.start)
    return atoms


def plays_role(sentence: str, rule: AtomRule) -> bool:
    """Whether the sentence is about the field the atom kind has a counterpart for."""
    if rule.field_role is None:
        return False
    if not rule.role_keywords:
        return True
    low = sentence.lower()
    return any(k in low for k in rule.role_keywords)
