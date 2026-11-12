"""The arithmetic, against published table values and against itself."""

from __future__ import annotations

import math

import pytest

from prg import stats
from prg.exit_codes import PrgError

# Two-sided 5% critical values of Student's t, from a published table.
T_TABLE = {1: 12.706, 2: 4.303, 5: 2.571, 9: 2.262, 10: 2.228, 20: 2.086, 29: 2.045, 30: 2.042, 60: 2.000, 120: 1.980, 199: 1.972}


@pytest.mark.parametrize("df,crit", sorted(T_TABLE.items()))
def test_the_two_sided_p_at_a_table_critical_value_is_five_percent_to_three_decimals(df, crit):
    assert abs(stats.t_two_sided_p(crit, df) - 0.05) < 0.0015


@pytest.mark.parametrize("df,crit", sorted(T_TABLE.items()))
def test_the_quantile_at_ninety_seven_and_a_half_percent_reproduces_the_table_to_two_decimals(df, crit):
    assert abs(stats.t_quantile(0.975, df) - crit) < 0.006


def test_the_t_cdf_is_one_half_at_zero_for_any_degrees_of_freedom():
    for df in (1, 3, 29, 500):
        assert abs(stats.t_cdf(0.0, df) - 0.5) < 1e-12


def test_the_t_cdf_is_symmetric():
    for t in (0.3, 1.7, 4.2):
        assert abs(stats.t_cdf(t, 12) + stats.t_cdf(-t, 12) - 1.0) < 1e-12


def test_the_t_cdf_with_many_degrees_of_freedom_approaches_the_normal():
    from statistics import NormalDist

    for t in (-2.0, -0.5, 1.0, 2.5):
        assert abs(stats.t_cdf(t, 200000) - NormalDist().cdf(t)) < 1e-4


def test_the_t_cdf_refuses_non_positive_degrees_of_freedom():
    with pytest.raises(PrgError):
        stats.t_cdf(1.0, 0)


def test_the_quantile_refuses_a_probability_outside_the_open_interval():
    with pytest.raises(PrgError):
        stats.t_quantile(1.0, 10)
    with pytest.raises(PrgError):
        stats.t_quantile(0.0, 10)


def test_the_incomplete_beta_is_zero_at_zero_and_one_at_one():
    assert stats.incomplete_beta(2.0, 3.0, 0.0) == 0.0
    assert stats.incomplete_beta(2.0, 3.0, 1.0) == 1.0


def test_the_incomplete_beta_with_a_and_b_one_is_the_identity():
    for x in (0.1, 0.5, 0.9):
        assert abs(stats.incomplete_beta(1.0, 1.0, x) - x) < 1e-12


def test_a_paired_test_reports_mean_spread_and_a_p_that_matches_the_table():
    diffs = [0.5, 0.2, 0.9, 0.1, 0.7, 0.3, 0.6, 0.4, 0.8, 0.0]
    r = stats.paired_t(diffs, 0.05)
    assert r.n == 10 and r.df == 9
    assert abs(r.mean_diff - 0.45) < 1e-12
    assert r.t > 0 and r.p < 0.01 and r.decided and r.direction == "better"
    assert r.ci_low < r.mean_diff < r.ci_high


def test_a_paired_test_with_no_effect_is_undecided():
    r = stats.paired_t([0.3, -0.3, 0.2, -0.2, 0.1, -0.1], 0.05)
    assert r.direction == "undecided" and not r.decided


def test_a_paired_test_with_a_negative_effect_is_worse():
    r = stats.paired_t([-1.0, -0.8, -1.2, -0.9, -1.1], 0.05)
    assert r.direction == "worse"


def test_a_paired_test_with_identical_differences_has_zero_spread_and_decides():
    r = stats.paired_t([0.5, 0.5, 0.5, 0.5], 0.05)
    assert r.sd_diff == 0.0 and r.p == 0.0 and r.direction == "better"
    z = stats.paired_t([0.0, 0.0, 0.0], 0.05)
    assert z.p == 1.0 and z.direction == "undecided"


def test_a_paired_test_needs_three_pairs():
    with pytest.raises(PrgError):
        stats.paired_t([0.1, 0.2], 0.05)


def test_the_noise_floor_falls_with_n_and_rises_with_the_spread():
    a = stats.minimum_detectable_effect(30, 0.8, 0.05, 0.8)
    b = stats.minimum_detectable_effect(120, 0.8, 0.05, 0.8)
    c = stats.minimum_detectable_effect(30, 1.6, 0.05, 0.8)
    assert b < a < c
    assert abs(c - 2 * a) < 1e-9


def test_the_noise_floor_at_thirty_matches_the_hand_formula():
    sd = 0.8
    expected = (2.045 + 0.854) * sd / math.sqrt(30)
    assert abs(stats.minimum_detectable_effect(30, sd, 0.05, 0.8) - expected) < 0.002


def test_the_noise_floor_needs_three_pairs():
    with pytest.raises(PrgError):
        stats.minimum_detectable_effect(2, 1.0, 0.05, 0.8)


def test_the_minimum_n_is_the_first_n_whose_floor_is_at_or_below_the_effect():
    n = stats.minimum_n(0.3, 0.8, 0.05, 0.8)
    assert n is not None
    assert stats.minimum_detectable_effect(n, 0.8, 0.05, 0.8) <= 0.3
    assert stats.minimum_detectable_effect(n - 1, 0.8, 0.05, 0.8) > 0.3


def test_the_minimum_n_by_bisection_equals_a_linear_walk_for_small_effects():
    for effect in (0.9, 0.6, 0.45, 0.33):
        walked = next(n for n in range(3, 2000) if stats.minimum_detectable_effect(n, 1.0, 0.05, 0.8) <= effect)
        assert stats.minimum_n(effect, 1.0, 0.05, 0.8) == walked


def test_the_minimum_n_is_none_for_a_zero_effect_and_three_for_a_zero_spread():
    assert stats.minimum_n(0.0, 1.0, 0.05, 0.8) is None
    assert stats.minimum_n(0.2, 0.0, 0.05, 0.8) == 3


def test_the_minimum_n_is_none_above_the_cap():
    assert stats.minimum_n(0.0001, 1.0, 0.05, 0.8, cap=1000) is None


def test_the_sign_test_is_the_exact_two_sided_binomial():
    r = stats.sign_test([1, 1, 1, -1, 0, 1, 1, 1, 1, 1])
    assert (r.wins, r.losses, r.ties) == (8, 1, 1)
    assert abs(r.p - 2 * (1 + 9) / 512) < 1e-12


def test_the_sign_test_with_only_ties_has_p_one():
    assert stats.sign_test([0.0, 0.0]).p == 1.0


def test_the_sign_test_p_never_exceeds_one():
    assert stats.sign_test([1, -1, 1, -1]).p == 1.0


def test_cohen_kappa_is_one_for_identical_labels_and_zero_for_chance():
    assert stats.cohen_kappa(["a", "b", "a"], ["a", "b", "a"]) == 1.0
    assert abs(stats.cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"])) < 1e-12


def test_cohen_kappa_matches_a_hand_computed_example():
    a = list("aabbc")
    b = list("aabcc")
    assert abs(stats.cohen_kappa(a, b) - 0.7058823529) < 1e-9


def test_cohen_kappa_refuses_mismatched_lists():
    with pytest.raises(PrgError):
        stats.cohen_kappa(["a"], ["a", "b"])


def test_the_agreement_rate_counts_matching_positions():
    assert stats.agreement_rate(list("abab"), list("abba")) == 0.5


def test_spearman_is_one_for_a_monotone_relation_and_handles_ties():
    assert abs(stats.spearman([1, 2, 3, 4], [10, 20, 30, 40]) - 1.0) < 1e-12
    assert abs(stats.spearman([1, 2, 3, 4], [1, 3, 2, 4]) - 0.8) < 1e-12
    assert abs(stats.spearman([1, 1, 2, 2], [1, 1, 2, 2]) - 1.0) < 1e-12


def test_spearman_is_zero_when_one_side_is_constant():
    assert stats.spearman([1, 2, 3], [5, 5, 5]) == 0.0


def test_spearman_refuses_short_or_mismatched_lists():
    with pytest.raises(PrgError):
        stats.spearman([1], [2])


def test_the_bootstrap_is_deterministic_for_a_seed_and_brackets_the_mean():
    diffs = [0.1, 0.3, -0.2, 0.5, 0.2, 0.0, 0.4] * 5
    a = stats.bootstrap_ci(diffs, 500, 11, 0.05)
    b = stats.bootstrap_ci(diffs, 500, 11, 0.05)
    assert a == b
    assert a[0] < stats.mean(diffs) < a[1]
    assert stats.bootstrap_ci(diffs, 500, 12, 0.05) != a
