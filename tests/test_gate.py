"""The two dimensions, the decision rule, and the arithmetic beyond one verdict."""

from __future__ import annotations

import itertools

import pytest

from prg.exit_codes import BLOCKED, SHIP, UNDECIDED, PrgError
from prg.gate import (
    Dimension,
    decide,
    draws,
    first_clearing_n,
    grounding_dimension,
    load_context,
    prefix_sweep,
    review_dimension,
    reviewer_agreement,
    run_gate,
)
from prg.stats import PairedTest

from .helpers import ORDER, edit, paths, set_score, set_summary

C1 = "500000000000001AAA"


def _dim(direction: str, effect: float = 0.3) -> Dimension:
    if direction == "refused":
        return Dimension("x", 0, None, "refused", None, None, 0.0, 0.0, "why")
    p = 0.01 if direction != "undecided" else 0.4
    signed = effect if direction == "better" else -effect if direction == "worse" else 0.1
    test = PairedTest(30, signed, 0.8, 0.146, signed / 0.146, 29, p, signed - 0.3, signed + 0.3, 0.05)
    return Dimension("x", 30, test, direction, 0.42, 60, 3.0, 3.0 + signed)


@pytest.mark.parametrize("reviews,grounding", list(itertools.product(["better", "worse", "undecided", "refused"], repeat=2)))
def test_the_decision_rule_blocks_on_any_worse_ships_only_on_better_reviews_and_cannot_decide_otherwise(reviews, grounding):
    code, reasons = decide(_dim(reviews), _dim(grounding))
    if "worse" in (reviews, grounding):
        assert code == BLOCKED
    elif reviews == "better" and grounding in ("better", "undecided"):
        assert code == SHIP
    else:
        assert code == UNDECIDED
    assert reasons


def test_a_demonstrated_regression_wins_over_an_undecided_or_refused_dimension():
    assert decide(_dim("undecided"), _dim("worse"))[0] == BLOCKED
    assert decide(_dim("refused"), _dim("worse"))[0] == BLOCKED
    assert decide(_dim("worse"), _dim("refused"))[0] == BLOCKED


def test_an_undecided_review_prints_the_minimum_n_in_its_reason():
    _, reasons = decide(_dim("undecided"), _dim("better"))
    assert any("would need 60 reviews" in r for r in reasons)


def test_an_undecided_review_with_a_zero_effect_says_no_finite_number():
    d = _dim("undecided")
    d.min_n = None
    _, reasons = decide(d, _dim("better"))
    assert any("no finite number" in r for r in reasons)


def test_the_mini_corpus_gate_ships_v2_on_its_four_reviews_when_grounding_is_not_worse(mini_ctx):
    r = run_gate(mini_ctx, "v1", "v2", "all")
    assert r.reviews.direction == "better"
    assert r.grounding.direction in ("undecided", "worse")


def test_the_mini_corpus_grounding_counts_bad_claims_per_case(mini_ctx):
    d = grounding_dimension(mini_ctx, "v1", "v2")
    assert d.n == 4 and d.baseline_mean == 0.0 and d.candidate_mean == pytest.approx(1.0)
    assert d.test.mean_diff == pytest.approx(-1.0)


def test_the_same_version_on_both_sides_is_refused(mini_ctx):
    with pytest.raises(PrgError, match="the same version"):
        run_gate(mini_ctx, "v1", "v1")


def test_an_unknown_version_is_refused_by_name(mini_ctx):
    with pytest.raises(PrgError, match="no version 'v9'"):
        run_gate(mini_ctx, "v1", "v9")


def test_a_version_whose_contract_names_a_missing_field_has_its_grounding_refused(mini):
    path = mini / "force-app" / "main" / "default" / "genAiPromptTemplates" / "Mini_Summary.genAiPromptTemplate-meta.xml"
    edit(path, "Facts: {!$Apex:Grounder.Prompt}", "Facts: {!$Apex:Grounder.Prompt} {!$Input:Case.Rating}")
    ctx = load_context(**paths(mini))
    assert "v2" in ctx.refused and "Rating" in ctx.refused["v2"]
    r = run_gate(ctx, "v1", "v2", "all")
    assert r.grounding.direction == "refused" and r.exit_code == UNDECIDED
    with pytest.raises(PrgError, match="grounding refused"):
        ctx.grounding("v2")


def test_drifted_prompts_are_refused_at_load_with_the_first_case_named(mini):
    edit(mini / "generations" / "v1" / f"{C1}.json", "Summarize the case.", "Summarise the case.")
    with pytest.raises(PrgError, match="drifted apart"):
        load_context(**paths(mini))


def test_a_missing_reviews_directory_makes_the_review_dimension_refused(tmp_path):
    from .helpers import write_corpus

    project = write_corpus(tmp_path, with_reviews=False)
    ctx = load_context(**paths(project))
    assert ctx.reviews is None
    r = run_gate(ctx, "v1", "v2")
    assert r.reviews.direction == "refused" and r.exit_code == UNDECIDED


def test_a_version_without_generations_is_skipped_at_load_and_refused_in_grounding(mini):
    import shutil

    shutil.rmtree(mini / "generations" / "v2")
    ctx = load_context(**paths(mini))
    assert "v2" not in ctx.generations
    with pytest.raises(PrgError, match="no generations loaded"):
        ctx.grounding("v2")
    assert grounding_dimension(ctx, "v1", "v2").direction == "refused"


def test_fewer_than_three_shared_cases_refuses_the_grounding_dimension(mini):
    for case_id in ORDER[:2]:
        (mini / "generations" / "v2" / f"{case_id}.json").unlink()
    ctx = load_context(**paths(mini))
    assert grounding_dimension(ctx, "v1", "v2").direction == "refused"


def test_a_lower_candidate_score_is_a_demonstrated_regression(mini):
    for reviewer in ("reviewer_a", "reviewer_b", "reviewer_c"):
        for case_id in ORDER:
            set_score(mini, reviewer, case_id, "v2", "1")
    ctx = load_context(**paths(mini))
    r = run_gate(ctx, "v1", "v2", "all")
    assert r.reviews.direction == "worse" and r.exit_code == BLOCKED


def test_more_bad_claims_in_the_candidate_block_even_when_reviews_prefer_it(mini):
    for case_id in ORDER:
        set_summary(
            mini,
            "v2",
            case_id,
            "The case is Low priority. The case is Medium priority. A replacement shipped under RMA-1 on 2026-01-01.",
        )
    ctx = load_context(**paths(mini))
    r = run_gate(ctx, "v1", "v2", "all")
    assert r.reviews.direction == "better" and r.grounding.direction == "worse" and r.exit_code == BLOCKED


def test_the_review_dimension_carries_a_sign_test_and_a_bootstrap_interval(mini_ctx):
    d = review_dimension(mini_ctx, "v1", "v2", ORDER)
    assert d.sign is not None and d.sign.wins == 4 and d.sign.ties == 0
    assert d.bootstrap is not None and d.bootstrap[0] <= d.test.mean_diff <= d.bootstrap[1]
    assert d.as_dict()["sign"]["wins"] == 4


def test_the_prefix_sweep_walks_the_committed_order_and_names_the_first_clearing_n(ctx):
    rows = prefix_sweep(ctx, "v1", "v3", start=10)
    assert [r["n"] for r in rows] == list(range(10, 201))
    n = first_clearing_n(rows)
    assert n is not None and rows[n - 10]["direction"] == "better" and all(r["direction"] != "better" for r in rows[: n - 10])


def test_a_sweep_that_never_clears_has_no_clearing_n():
    assert first_clearing_n([{"n": 10, "direction": "undecided"}]) is None


def test_the_draws_are_seeded_and_count_clearing_and_wrong_way_samples(mini_ctx):
    a = draws(mini_ctx, "v1", "v2")
    b = draws(mini_ctx, "v1", "v2")
    assert a == b and a["count"] == 20 and a["size"] == 3
    assert 0 <= a["clearAlpha"] <= 20 and 0 <= a["wrongWay"] <= 20


def test_reviewer_agreement_reports_every_pair_and_the_means(mini_ctx):
    a = reviewer_agreement(mini_ctx, "v1", "v2", ORDER)
    assert [(p["a"], p["b"]) for p in a["pairs"]] == [
        ("reviewer_a", "reviewer_b"),
        ("reviewer_a", "reviewer_c"),
        ("reviewer_b", "reviewer_c"),
    ]
    assert 0 <= a["meanAgreementPct"] <= 100


def test_a_gate_result_serialises_both_dimensions_and_the_exit_code(mini_ctx):
    r = run_gate(mini_ctx, "v1", "v2", "all").as_dict()
    assert set(r) == {"baseline", "candidate", "reviewedSet", "reviews", "grounding", "exitCode", "reasons"}
    assert r["reviews"]["n"] == 4 and r["grounding"]["n"] == 4


def test_the_reviewed_set_defaults_to_the_policy(mini_ctx):
    assert run_gate(mini_ctx, "v1", "v2").reviewed_set == "first30"
