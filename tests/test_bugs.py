"""Bugs hit during the build, each pinned with the story that found it."""

from __future__ import annotations

import random

from prg.adapters import fixture as standin
from prg.claims import extract_atoms, load_grammar
from prg.gate import load_context
from prg.stats import minimum_detectable_effect, minimum_n

from .helpers import GRAMMAR, paths, set_summary

C1 = "500000000000001AAA"


def test_newest_comment_does_not_support_the_status_new(mini):
    """The first grounder tested containment with a plain substring, so the Apex provider's text
    "Newest comment: 2026-02-11" supported a displaced status of New on a case that was Working,
    and the planted contradiction came back supported. Whole-word containment fixed it; the first
    comparison against the planted truth is what found it."""
    s = load_context(**paths(mini)).grounding("v2")  # v2 merges the provider
    set_summary(mini, "v2", C1, "The status is currently New.")
    s = load_context(**paths(mini)).grounding("v2")[C1]
    assert s.claims[0].verdict == "contradicted"
    assert s.claims[0].atoms[0].source_ref == "Status is Working"


def test_a_product_name_ending_in_a_digit_is_not_eaten_by_the_duration_rule():
    """ "Aero 2 units carry a 24-month warranty" lost its product atom because the duration rule ran
    first and claimed "2 units"; thirteen planted mis-groundings in v3 came back unverifiable.
    Vocabulary rules now run before pattern rules, and `units` is no longer a unit."""
    grammar = load_grammar(GRAMMAR)
    atoms = extract_atoms("Aero 2 units carry a 24-month warranty.", grammar, {"Product__c": ["Aero 2"]})
    assert [(a.kind, a.value) for a in atoms] == [("product", "Aero 2"), ("duration", "24-month")]


def test_a_displaced_atom_lands_on_the_sentence_the_truth_names():
    """The stand-in once inserted the invented sentence before displacing an atom by index, so a
    displacement aimed at the state sentence sometimes hit the invented one and the truth planted
    a contradiction on a sentence the grounder graded unsupported (seven of them in v2). The
    displacement now runs before the insertion; this test drives the stand-in through every seed
    that produces both faults and checks the contradiction's sentence is the one it edited."""
    from prg.exports import read_exports
    from prg.metadata import find_template

    from .conftest import FIXTURE

    exports = read_exports(FIXTURE / "data")
    template = find_template(FIXTURE, ["Input", "RelatedList", "Flow", "Apex", "EinsteinSearch"])
    model = {
        "fluency": 0.2,
        "omit_detail": 0.0,
        "invent_sentence": 1.0,
        "contradict_atom": 1.0,
        "quote_chunk": 0.0,
        "add_sentiment": 0.0,
        "invented_templates": ["Invoice INV-{inv} was issued on {date} for the repair."],
    }
    contacts = sorted({c.value("Contact.Name") for c in exports.cases.values()})
    checked = 0
    for seed in range(40):
        case = exports.case(f"500{seed + 1:012d}AAA")
        text, faults = standin.generate(case, template.version("v2"), random.Random(seed), model, contacts)
        contradiction = [f for f in faults if f.kind in ("contradicted", "unsupported") and f.atom_kind != "identifier"]
        for fault in contradiction:
            assert fault.sentence in text.split(". ") or fault.sentence in text
            assert "INV-" not in fault.sentence
            checked += 1
    assert checked >= 40


def test_an_invented_date_is_never_a_date_the_case_already_had():
    """Two planted unsupported dates came back supported because a shifted date landed on the case's
    opened date or on a comment date. The stand-in now shifts until the date is in no source."""
    from prg.exports import read_exports
    from prg.metadata import find_template

    from .conftest import FIXTURE

    exports = read_exports(FIXTURE / "data")
    template = find_template(FIXTURE, ["Input", "RelatedList", "Flow", "Apex", "EinsteinSearch"])
    model = {
        "fluency": 0.0,
        "omit_detail": 0.0,
        "invent_sentence": 1.0,
        "contradict_atom": 0.0,
        "quote_chunk": 0.0,
        "add_sentiment": 0.0,
        "invented_templates": ["The customer was told a firmware update would arrive on {date}."],
    }
    for n in range(1, 60):
        case = exports.case(f"500{n:012d}AAA")
        _, faults = standin.generate(case, template.version("v1"), random.Random(n), model, [])
        (fault,) = faults
        haystack = " ".join(list(case.fields.values()) + [c.body + c.created for c in case.comments])
        assert fault.atom_kind == "date"
        date = fault.sentence.split("on ")[1].rstrip(".")
        assert date not in haystack


def test_the_minimum_n_is_found_by_bisection_not_by_walking():
    """`prg power` took minutes on the grounding dimension because the first minimum_n walked n
    upwards one at a time to 3002, computing two t quantiles per step. Bracketing and bisection
    give the same answer; the test pins equality against a walk on a case small enough to walk."""
    walked = next(n for n in range(3, 5000) if minimum_detectable_effect(n, 1.0, 0.05, 0.8) <= 0.25)
    assert minimum_n(0.25, 1.0, 0.05, 0.8) == walked
