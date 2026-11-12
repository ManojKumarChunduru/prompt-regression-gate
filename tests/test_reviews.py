"""The review reader: pairing, preferences, the reviewed sets, and the refusals that keep n honest."""

from __future__ import annotations

import pytest

from prg.exit_codes import PrgError
from prg.policy import load_policy
from prg.reviews import read_reviews

from .conftest import FIXTURE
from .helpers import ORDER, edit, set_score


def test_the_fixture_reviews_hold_three_reviewers_over_two_hundred_cases_and_three_versions():
    r = read_reviews(FIXTURE / "reviews", load_policy(None))
    assert r.reviewers == ["reviewer_a", "reviewer_b", "reviewer_c"]
    assert len(r.order) == 200 and len(r.rows) == 1800
    assert r.versions() == ["v1", "v2", "v3"]


def test_the_canonical_thirty_is_the_first_thirty_of_the_order_and_all_is_everything():
    r = read_reviews(FIXTURE / "reviews", load_policy(None))
    assert r.reviewed_set("first30") == r.order[:30]
    assert r.reviewed_set("all") == r.order
    with pytest.raises(PrgError, match="not first30 or all"):
        r.reviewed_set("some")


def test_every_score_is_between_one_and_five():
    r = read_reviews(FIXTURE / "reviews", load_policy(None))
    assert all(1 <= row.score <= 5 for row in r.rows)


def test_a_case_mean_is_the_mean_of_the_three_reviewers(mini):
    r = read_reviews(mini / "reviews", load_policy(None))
    assert r.case_mean("500000000000001AAA", "v1") == pytest.approx((3 + 3 + 4) / 3)
    assert r.case_mean("500000000000001AAA", "v2") == pytest.approx((4 + 4 + 5) / 3)


def test_paired_differences_are_candidate_minus_baseline_in_the_given_order(mini):
    r = read_reviews(mini / "reviews", load_policy(None))
    diffs = r.paired_differences("v1", "v2", ORDER)
    assert diffs == pytest.approx([1.0, 1.0, 1 / 3, 1.0])


def test_preferences_label_each_case_as_candidate_baseline_or_tie(mini):
    r = read_reviews(mini / "reviews", load_policy(None))
    assert r.preferences("reviewer_a", "v1", "v2", ORDER) == ["candidate", "candidate", "candidate", "candidate"]


def test_flagged_by_any_reviewer_is_true_only_where_one_flagged(mini):
    r = read_reviews(mini / "reviews", load_policy(None))
    assert r.flagged_by_any("500000000000001AAA", "v2") is True
    assert r.flagged_by_any("500000000000001AAA", "v1") is False


def test_a_score_outside_the_range_is_refused_with_the_file_and_row(mini):
    set_score(mini, "reviewer_b", "500000000000003AAA", "v1", "7")
    with pytest.raises(PrgError, match=r"reviewer_b.csv: row 2: score 7 is outside 1 to 5"):
        read_reviews(mini / "reviews", load_policy(None))


def test_a_non_integer_score_is_refused(mini):
    set_score(mini, "reviewer_b", "500000000000003AAA", "v1", "four")
    with pytest.raises(PrgError, match="is not an integer"):
        read_reviews(mini / "reviews", load_policy(None))


def test_a_missing_score_is_refused_because_n_would_shrink_silently(mini):
    path = mini / "reviews" / "reviewer_c.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(PrgError, match="n would shrink silently"):
        read_reviews(mini / "reviews", load_policy(None))


def test_a_duplicate_score_is_refused(mini):
    path = mini / "reviews" / "reviewer_c.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines + [lines[-1]]) + "\n", encoding="utf-8")
    with pytest.raises(PrgError, match="twice"):
        read_reviews(mini / "reviews", load_policy(None))


def test_a_case_not_in_the_order_is_refused(mini):
    edit(mini / "reviews" / "reviewer_a.csv", "500000000000004AAA", "500000000000044AAA")
    with pytest.raises(PrgError, match="is not in order.txt"):
        read_reviews(mini / "reviews", load_policy(None))


def test_a_duplicate_in_the_order_is_refused(mini):
    edit(mini / "reviews" / "order.txt", "500000000000002AAA", "500000000000001AAA")
    with pytest.raises(PrgError, match="appears twice"):
        read_reviews(mini / "reviews", load_policy(None))


def test_a_missing_column_is_refused(mini):
    edit(mini / "reviews" / "reviewer_a.csv", "caseId,version,score,flagged", "caseId,version,points,flagged")
    with pytest.raises(PrgError, match="column 'score' is missing"):
        read_reviews(mini / "reviews", load_policy(None))


def test_a_missing_order_file_and_an_empty_directory_are_refused(tmp_path):
    with pytest.raises(PrgError, match="review order not found"):
        read_reviews(tmp_path, load_policy(None))
    (tmp_path / "order.txt").write_text("a\n", encoding="utf-8")
    with pytest.raises(PrgError, match="no reviewer CSV files"):
        read_reviews(tmp_path, load_policy(None))


def test_the_expected_versions_can_be_narrowed_to_those_with_generations(mini):
    r = read_reviews(mini / "reviews", load_policy(None), versions=["v1"])
    assert r.versions() == ["v1", "v2"]
