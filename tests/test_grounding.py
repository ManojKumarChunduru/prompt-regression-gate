"""Every verdict on the small corpus, bent one claim at a time."""

from __future__ import annotations

import pytest

from prg.claims import load_grammar
from prg.gate import load_context
from prg.grounding import census, ground, sources_for, vocabularies

from .helpers import GRAMMAR, edit, paths, refresh_prompts, set_summary

C1, C2, C3, C4 = "500000000000001AAA", "500000000000002AAA", "500000000000003AAA", "500000000000004AAA"


def _ground(mini, version, case_id, text):
    set_summary(mini, version, case_id, text)
    ctx = load_context(**paths(mini))
    return ctx.grounding(version)[case_id]


def test_the_vocabularies_come_from_the_export_and_the_chunk_index(mini_ctx):
    v = vocabularies(mini_ctx.exports)
    assert v["Product__c"] == ["Aero 2", "Pulse Band", "Nimbus Hub", "Orbit Cam"]
    assert v["Contact.Name"] == ["Priya Natarajan", "Daniel Okafor", "Mei Sato", "Tomas Novak"]


def test_the_sources_of_a_version_are_exactly_what_its_contract_merges(mini_ctx):
    case = mini_ctx.exports.case(C1)
    s1 = sources_for(mini_ctx.template.version("v1"), case)
    s2 = sources_for(mini_ctx.template.version("v2"), case)
    assert set(s1.fields) == {"Subject", "Description", "Priority", "Status", "Product__c", "Contact.Name", "Amount__c"}
    assert len(s1.comments) == 2 and s1.chunks == [] and s1.providers == []
    assert len(s2.chunks) == 3 and s2.providers[0][0] == "Grounder"


def test_a_clean_summary_is_supported_claim_by_claim(mini_ctx):
    s = mini_ctx.grounding("v1")[C1]
    assert [c.verdict for c in s.claims] == ["supported", "supported", "supported"]
    assert s.bad == 0 and s.checkable == 3
    money = [a for c in s.claims for a in c.atoms if a.kind == "money"][0]
    assert (money.verdict, money.source_kind, money.source_ref) == ("supported", "field", "Amount__c")


def test_a_wrong_priority_is_contradicted_with_the_field_value_named(mini):
    s = _ground(mini, "v1", C1, "The case is Low priority and the status is Working.")
    assert s.claims[0].verdict == "contradicted"
    atom = s.claims[0].atoms[0]
    assert (atom.kind, atom.value, atom.source_ref) == ("priority", "Low", "Priority is High")


def test_a_wrong_amount_in_an_offer_is_contradicted_and_a_bare_amount_is_unsupported(mini):
    s = _ground(mini, "v1", C1, "The agent offered a refund of $420.00. The figure $999.00 appears nowhere.")
    assert [c.verdict for c in s.claims] == ["contradicted", "unsupported"]
    assert s.claims[0].atoms[-1].source_ref == "Amount__c is 240.00"


def test_an_amount_the_comments_carry_is_supported_even_when_the_field_differs(mini):
    edit(mini / "data" / "Case.csv", "240.00", "300.00")
    refresh_prompts(mini)
    s = _ground(mini, "v1", C1, "The agent offered a refund of $240.00.")
    assert s.claims[0].verdict == "supported"
    assert s.claims[0].atoms[-1].source_kind == "comment"


def test_an_amount_matches_numerically_not_textually(mini):
    s = _ground(mini, "v1", C1, "A refund of $240 was offered.")
    assert s.claims[0].verdict == "supported"


def test_a_date_from_nowhere_is_unsupported_never_contradicted(mini):
    s = _ground(mini, "v1", C1, "Priya Natarajan reported it since 2026-02-07.")
    assert s.claims[0].verdict == "unsupported"
    assert [a.verdict for a in s.claims[0].atoms] == ["supported", "unsupported"]


def test_an_identifier_from_nowhere_is_unsupported(mini):
    s = _ground(mini, "v1", C4, "A replacement unit was shipped under RMA-55001 on 2026-05-04.")
    assert s.claims[0].verdict == "unsupported"
    assert [(a.kind, a.verdict) for a in s.claims[0].atoms] == [
        ("action", "supported"),
        ("identifier", "unsupported"),
        ("date", "supported"),
    ]


def test_another_customers_name_is_contradicted(mini):
    s = _ground(mini, "v1", C1, "Mei Sato reported that the Aero 2 stops charging since 2026-02-01.")
    assert s.claims[0].verdict == "contradicted"
    assert s.claims[0].atoms[0].source_ref == "Contact.Name is Priya Natarajan"


def test_another_product_is_contradicted_unless_a_comment_names_it(mini):
    s = _ground(mini, "v1", C1, "The customer also owns a Pulse Band.")
    assert s.claims[0].verdict == "contradicted"


def test_a_chunk_supports_a_claim_only_when_the_version_merges_the_retriever(mini):
    text = "The knowledge base notes that Aero 2 units carry a 24-month warranty from the purchase date."
    assert _ground(mini, "v1", C1, text).claims[0].verdict == "unsupported"
    s = _ground(mini, "v2", C1, text)
    assert s.claims[0].verdict == "supported"
    assert [(a.kind, a.source_kind) for a in s.claims[0].atoms] == [("product", "field"), ("duration", "chunk")]


def test_a_chunk_about_another_product_mis_grounds_the_claim(mini):
    s = _ground(mini, "v2", C1, "The knowledge base notes that Pulse Band straps are replaced free within 12 months.")
    assert s.claims[0].verdict == "misgrounded"
    atom = s.claims[0].atoms[0]
    assert atom.kind == "product" and atom.source_kind == "chunk" and "case is Aero 2" in atom.source_ref


def test_a_chunk_with_no_product_applies_to_every_case(mini):
    s = _ground(mini, "v2", C1, "A refund takes 10 days to reach the original card.")
    assert s.claims[0].verdict == "supported"
    assert [a.source_kind for a in s.claims[0].atoms] == ["comment", "chunk"]


def test_the_provider_text_is_a_source_for_the_version_that_merges_it(mini):
    assert _ground(mini, "v2", C1, "There were 2 comments on 2026-02-11.").claims[0].verdict == "supported"


def test_a_sentence_with_no_atom_is_unverifiable_and_not_bad(mini):
    s = _ground(mini, "v1", C1, "The customer sounds frustrated and wants a quick resolution.")
    assert s.claims[0].verdict == "unverifiable" and s.bad == 0 and s.checkable == 0


def test_a_claim_takes_the_worst_verdict_of_its_atoms(mini):
    s = _ground(mini, "v2", C1, "Mei Sato was told that Pulse Band straps are replaced free within 12 months under RMA-1234.")
    assert s.claims[0].verdict == "contradicted"
    assert sorted(a.verdict for a in s.claims[0].atoms) == ["contradicted", "misgrounded", "misgrounded", "unsupported"]


def test_the_census_counts_claims_verdicts_and_first_supporting_sources(mini_ctx):
    c = census(mini_ctx.grounding("v2"))
    assert c["summaries"] == 4 and c["claims"] == sum(len(s.claims) for s in mini_ctx.grounding("v2").values())
    assert c["bad"] == c["unsupported"] + c["contradicted"] + c["misgrounded"]
    assert c["contradicted"] == 2 and c["misgrounded"] == 1 and c["unsupported"] == 1 and c["unverifiable"] == 1
    assert sum(c["by_source"].values()) == c["supported"]


def test_grounding_a_generation_directly_matches_the_context(mini_ctx):
    grammar = load_grammar(GRAMMAR)
    g = mini_ctx.generations["v1"][C1]
    direct = ground(g, mini_ctx.template.version("v1"), mini_ctx.exports, grammar, mini_ctx.vocab)
    assert direct.counts() == mini_ctx.grounding("v1")[C1].counts()


@pytest.mark.parametrize("case_id", [C1, C2, C3, C4])
def test_the_small_corpus_v1_summaries_are_all_supported(mini_ctx, case_id):
    assert mini_ctx.grounding("v1")[case_id].bad == 0
