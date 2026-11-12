"""The stand-in model: every fault it can apply, recorded as it applies it."""

from __future__ import annotations

import random

import pytest

from prg.adapters import fixture as standin
from prg.exports import read_exports
from prg.metadata import find_template

from .conftest import FIXTURE

FAMILIES = ["Input", "RelatedList", "Flow", "Apex", "EinsteinSearch"]
QUIET = {
    "fluency": 0.0,
    "omit_detail": 0.0,
    "invent_sentence": 0.0,
    "contradict_atom": 0.0,
    "quote_chunk": 0.0,
    "add_sentiment": 0.0,
    "invented_templates": ["Invoice INV-{inv} was issued on {date} for the repair."],
}


@pytest.fixture(scope="module")
def corpus():
    exports = read_exports(FIXTURE / "data")
    template = find_template(FIXTURE, FAMILIES)
    contacts = sorted({c.value("Contact.Name") for c in exports.cases.values()})
    return exports, template, contacts


def test_a_quiet_model_writes_the_report_the_state_and_the_details_with_no_fault(corpus):
    exports, template, contacts = corpus
    case = exports.case("500000000000001AAA")
    text, faults = standin.generate(case, template.version("v1"), random.Random(1), QUIET, contacts)
    assert faults == []
    assert text.startswith(f"{case.fields['Contact.Name']} reported that the {case.fields['Product__c']}")
    assert f"The case is {case.fields['Priority']} priority and the status is {case.fields['Status']}." in text


def test_the_fluent_model_phrases_the_same_facts_differently(corpus):
    exports, template, contacts = corpus
    case = exports.case("500000000000001AAA")
    text, _ = standin.generate(case, template.version("v2"), random.Random(1), {**QUIET, "fluency": 0.2}, contacts)
    assert "contacted support because" in text and "It is a" in text


def test_quoting_an_off_product_chunk_is_recorded_as_a_mis_grounding(corpus):
    exports, template, contacts = corpus
    off_cases = [c for c in exports.cases.values() if any(k.product and k.product != c.fields["Product__c"] for k in c.chunks)]
    assert off_cases
    case = off_cases[0]
    _, faults = standin.generate(case, template.version("v3"), random.Random(1), {**QUIET, "quote_chunk": 1.0}, contacts)
    assert [f.kind for f in faults] == ["misgrounded"] and faults[0].displaced == case.fields["Product__c"]


def test_quoting_the_top_chunk_of_the_right_product_is_not_a_fault(corpus):
    exports, template, contacts = corpus
    clean = [c for c in exports.cases.values() if all(not k.product or k.product == c.fields["Product__c"] for k in c.chunks)]
    text, faults = standin.generate(clean[0], template.version("v3"), random.Random(1), {**QUIET, "quote_chunk": 1.0}, contacts)
    assert faults == [] and "The knowledge base notes that" in text


def test_a_version_without_the_retriever_never_quotes_a_chunk(corpus):
    exports, template, contacts = corpus
    text, faults = standin.generate(
        exports.case("500000000000001AAA"), template.version("v2"), random.Random(1), {**QUIET, "quote_chunk": 1.0}, contacts
    )
    assert "knowledge base" not in text and faults == []


def test_an_omission_drops_a_detail_sentence_and_records_it(corpus):
    exports, template, contacts = corpus
    case = exports.case("500000000000001AAA")
    text, faults = standin.generate(case, template.version("v1"), random.Random(3), {**QUIET, "omit_detail": 1.0}, contacts)
    assert [f.kind for f in faults] == ["omission"] and faults[0].sentence not in text


def test_every_displacement_kind_appears_over_enough_seeds_with_the_displaced_value_recorded(corpus):
    exports, template, contacts = corpus
    seen = {}
    for n in range(1, 120):
        case = exports.case(f"500{n:012d}AAA")
        text, faults = standin.generate(
            case, template.version("v1"), random.Random(n), {**QUIET, "contradict_atom": 1.0}, contacts
        )
        (fault,) = faults
        seen.setdefault(fault.atom_kind, fault)
        assert fault.atom in text and fault.atom != fault.displaced
        if fault.atom_kind == "money":
            assert (
                fault.kind == "contradicted"
                and fault.atom.startswith("$")
                and fault.displaced == f"${float(case.fields['Amount__c']):,.2f}"
            )
        if fault.atom_kind == "date":
            assert fault.kind == "unsupported"
    assert set(seen) == {"priority", "status", "contact", "date", "money"}


def test_a_sentiment_sentence_is_recorded_as_unverifiable_and_sits_last(corpus):
    exports, template, contacts = corpus
    text, faults = standin.generate(
        exports.case("500000000000001AAA"), template.version("v1"), random.Random(1), {**QUIET, "add_sentiment": 1.0}, contacts
    )
    assert [f.kind for f in faults] == ["unverifiable"] and text.endswith(faults[0].sentence)
