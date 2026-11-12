"""Gives every atom of every claim a verdict against the sources the template merged in.

Supported: a merged field, a related comment, a data provider's output or a retrieved chunk
contains the atom. Contradicted: the atom plays a role that has a field counterpart in the
contract, and that field holds a different value, and no comment says the atom. Mis-grounded: only
a retrieved chunk contains the atom and that chunk is about another product than the case (a
chunk with no product applies to every case).
Unsupported: nothing in the resolved prompt contains it. Unverifiable: the claim has no atom.
The contract is strict on purpose: a claim supported by a field the template did not merge in
is unsupported, because the model could not have read it (ADR-002).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .claims import Atom, Grammar, extract_atoms, plays_role, split_sentences
from .exports import Case, Exports
from .generations import Generation, render_provider
from .metadata import TemplateVersion

BAD = ("contradicted", "misgrounded", "unsupported")


@dataclass
class AtomVerdict:
    kind: str
    value: str
    verdict: str
    source_kind: str  # field, comment, chunk, provider, none
    source_ref: str  # field name, comment id, chunk id, provider name, or the contradicting value
    sentence: int


@dataclass
class Claim:
    index: int
    text: str
    verdict: str
    atoms: list[AtomVerdict] = field(default_factory=list)


@dataclass
class GroundedSummary:
    version: str
    case_id: str
    claims: list[Claim]

    def count(self, verdict: str) -> int:
        return sum(1 for c in self.claims if c.verdict == verdict)

    @property
    def bad(self) -> int:
        return sum(1 for c in self.claims if c.verdict in BAD)

    @property
    def checkable(self) -> int:
        return sum(1 for c in self.claims if c.verdict != "unverifiable")

    def counts(self) -> dict[str, int]:
        return {v: self.count(v) for v in ("supported", "unsupported", "contradicted", "misgrounded", "unverifiable")}


@dataclass
class Sources:
    """What the resolved prompt of one version contains for one case."""

    fields: dict[str, str]
    comments: list[tuple[str, str]]  # (id, body)
    chunks: list[tuple[str, str, str]]  # (id, product, text)
    providers: list[tuple[str, str]]  # (name, text)


def vocabularies(exports: Exports) -> dict[str, list[str]]:
    products: list[str] = []
    contacts: list[str] = []
    for case in exports.cases.values():
        p = case.value("Product__c") or ""
        if p and p not in products:
            products.append(p)
        c = case.value("Contact.Name") or ""
        if c and c not in contacts:
            contacts.append(c)
        for chunk in case.chunks:
            if chunk.product and chunk.product not in products:
                products.append(chunk.product)
    return {"Product__c": products, "Contact.Name": contacts}


def sources_for(version: TemplateVersion, case: Case) -> Sources:
    fields = {name: (case.value(name) or "") for name in version.fields}
    # A comment is a source with its date: the related list renders "[date] body" into the prompt.
    comments = [(c.id, f"[{c.created}] {c.body}") for c in case.comments] if version.has("RelatedList") else []
    chunks = [(c.chunk_id, c.product, c.text) for c in case.chunks] if version.has("EinsteinSearch") else []
    providers = [
        (m.provider or "", render_provider(case, m.provider or "")) for m in version.merge_fields if m.family in ("Flow", "Apex")
    ]
    return Sources(fields, comments, chunks, providers)


def _money(value: str) -> float | None:
    cleaned = value.replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _contains(haystack: str, atom: Atom, case_insensitive: bool) -> bool:
    if atom.kind == "money":
        target = _money(atom.value)
        if target is None:
            return False
        for token in haystack.replace(",", "").split():
            found = _money(token.rstrip(".;:)"))
            if found is not None and abs(found - target) < 0.005:
                return True
        return False
    # Whole-word containment: "Newest comment" must not support the status New, which the first
    # grammar let through (a plain substring test); pinned by a test with that story.
    pattern = r"(?<![\w-])" + re.escape(atom.value) + r"(?![\w-])"
    return re.search(pattern, haystack, re.I if case_insensitive else 0) is not None


def judge_atom(atom: Atom, sentence: str, sources: Sources, case: Case, grammar: Grammar, index: int) -> AtomVerdict:
    rule = grammar.rule(atom.kind)
    ci = rule.case_insensitive
    for name, value in sources.fields.items():
        if value and _contains(value, atom, ci):
            return AtomVerdict(atom.kind, atom.value, "supported", "field", name, index)
    for cid, body in sources.comments:
        if _contains(body, atom, ci):
            return AtomVerdict(atom.kind, atom.value, "supported", "comment", cid, index)
    for pname, text in sources.providers:
        if _contains(text, atom, ci):
            return AtomVerdict(atom.kind, atom.value, "supported", "provider", pname, index)
    chunk_hits = [(cid, product) for cid, product, text in sources.chunks if _contains(text, atom, ci)]
    if chunk_hits:
        cid, product = chunk_hits[0]
        case_product = case.value("Product__c") or ""
        same = [c for c, p in chunk_hits if p == case_product or p == ""]
        if same:
            return AtomVerdict(atom.kind, atom.value, "supported", "chunk", same[0], index)
        return AtomVerdict(atom.kind, atom.value, "misgrounded", "chunk", f"{cid} ({product}, case is {case_product})", index)
    if rule.field_role and rule.field_role in sources.fields and plays_role(sentence, rule):
        actual = sources.fields[rule.field_role]
        if actual and not _contains(actual, atom, ci):
            return AtomVerdict(atom.kind, atom.value, "contradicted", "field", f"{rule.field_role} is {actual}", index)
    return AtomVerdict(atom.kind, atom.value, "unsupported", "none", "", index)


def ground(
    generation: Generation, version: TemplateVersion, exports: Exports, grammar: Grammar, vocab: dict[str, list[str]]
) -> GroundedSummary:
    case = exports.case(generation.case_id)
    sources = sources_for(version, case)
    claims: list[Claim] = []
    for index, sentence in enumerate(split_sentences(generation.text, grammar), start=1):
        atoms = extract_atoms(sentence, grammar, vocab)
        verdicts = [judge_atom(a, sentence, sources, case, grammar, index) for a in atoms]
        if not verdicts:
            claims.append(Claim(index, sentence, "unverifiable", []))
            continue
        worst = min(verdicts, key=lambda v: grammar.verdict_order.index(v.verdict))
        claims.append(Claim(index, sentence, worst.verdict, verdicts))
    return GroundedSummary(generation.version, generation.case_id, claims)


def ground_version(
    generations: dict[str, Generation], version: TemplateVersion, exports: Exports, grammar: Grammar, vocab: dict[str, list[str]]
) -> dict[str, GroundedSummary]:
    return {case_id: ground(g, version, exports, grammar, vocab) for case_id, g in generations.items()}


def census(grounded: dict[str, GroundedSummary]) -> dict:
    totals = {v: 0 for v in ("supported", "unsupported", "contradicted", "misgrounded", "unverifiable")}
    by_source = {"field": 0, "comment": 0, "chunk": 0, "provider": 0}
    claims = 0
    for summary in grounded.values():
        for claim in summary.claims:
            claims += 1
            totals[claim.verdict] += 1
            if claim.verdict == "supported":
                for a in claim.atoms:
                    if a.verdict == "supported":
                        by_source[a.source_kind] += 1
                        break
    totals["claims"] = claims
    totals["bad"] = totals["unsupported"] + totals["contradicted"] + totals["misgrounded"]
    totals["by_source"] = by_source
    totals["summaries"] = len(grounded)
    return totals
