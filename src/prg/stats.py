"""The arithmetic, in the standard library, tested against published table values.

A gate that needs scipy on the runner is a gate that does not run on the runner (ADR-003). What
the gate needs is small: Student's t distribution (through the regularised incomplete beta, by
continued fraction), the paired t test and its interval, the minimum detectable effect at a sample
size (the noise floor), the minimum sample size for an observed effect (central t quantiles
iterated to a fixed point, the approximation stated in ADR-001), the exact sign test, Cohen's
kappa, Spearman's rank correlation, and a seeded percentile bootstrap. No function reads a clock
or an unseeded random source.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from functools import lru_cache
from statistics import mean, stdev

from .exit_codes import PrgError

# Regularised incomplete beta, Numerical Recipes' continued fraction (betacf), with lgamma.


def _betacf(a: float, b: float, x: float) -> float:
    max_iter, eps, tiny = 300, 3e-14, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def incomplete_beta(a: float, b: float, x: float) -> float:
    """I_x(a, b), the regularised incomplete beta function."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def t_cdf(t: float, df: float) -> float:
    """P(T <= t) for Student's t with df degrees of freedom."""
    if df <= 0:
        raise PrgError(f"degrees of freedom must be positive, not {df}")
    x = df / (df + t * t)
    tail = 0.5 * incomplete_beta(df / 2.0, 0.5, x)
    return 1.0 - tail if t >= 0 else tail


def t_two_sided_p(t: float, df: float) -> float:
    return 2.0 * (1.0 - t_cdf(abs(t), df))


@lru_cache(maxsize=65536)
def t_quantile(p: float, df: float) -> float:
    """The t such that P(T <= t) = p, by bisection on the CDF.

    Cached: the sweep and the draws ask for the same quantiles thousands of times."""
    if not 0.0 < p < 1.0:
        raise PrgError(f"quantile probability must be strictly between 0 and 1, not {p}")
    lo, hi = -1000.0, 1000.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


@dataclass
class PairedTest:
    n: int
    mean_diff: float
    sd_diff: float
    se: float
    t: float
    df: int
    p: float
    ci_low: float
    ci_high: float
    alpha: float

    @property
    def decided(self) -> bool:
        return self.p < self.alpha

    @property
    def direction(self) -> str:
        """better, worse or undecided, from the candidate's point of view (diff = candidate minus baseline)."""
        if not self.decided:
            return "undecided"
        return "better" if self.mean_diff > 0 else "worse"


def paired_t(diffs: list[float], alpha: float) -> PairedTest:
    n = len(diffs)
    if n < 3:
        raise PrgError(f"a paired test needs at least 3 pairs, got {n}")
    m = mean(diffs)
    sd = stdev(diffs)
    df = n - 1
    if sd == 0.0:
        t = math.inf if m != 0 else 0.0
        p = 0.0 if m != 0 else 1.0
        return PairedTest(n, m, sd, 0.0, t, df, p, m, m, alpha)
    se = sd / math.sqrt(n)
    t = m / se
    p = t_two_sided_p(t, df)
    crit = t_quantile(1.0 - alpha / 2.0, df)
    return PairedTest(n, m, sd, se, t, df, p, m - crit * se, m + crit * se, alpha)


def minimum_detectable_effect(n: int, sd: float, alpha: float, power: float) -> float:
    """The smallest paired mean difference a sample of n clears at alpha with the given power: the noise floor."""
    if n < 3:
        raise PrgError(f"the noise floor needs at least 3 pairs, got {n}")
    df = n - 1
    return (t_quantile(1.0 - alpha / 2.0, df) + t_quantile(power, df)) * sd / math.sqrt(n)


def minimum_n(effect: float, sd: float, alpha: float, power: float, cap: int = 100000) -> int | None:
    """The smallest n whose noise floor is at or below the observed effect, by iteration on the central t
    quantiles (the approximation ADR-001 states). None above the cap or for a zero effect."""
    effect = abs(effect)
    if effect == 0.0 or sd == 0.0:
        return None if effect == 0.0 else 3
    if minimum_detectable_effect(cap, sd, alpha, power) > effect:
        return None
    # The floor falls monotonically with n, so bracket by doubling and then bisect; the first version
    # walked n upwards one at a time and took minutes on a floor in the thousands.
    lo, hi = 3, 3
    while minimum_detectable_effect(hi, sd, alpha, power) > effect:
        lo, hi = hi, min(cap, hi * 2)
    while lo < hi:
        mid = (lo + hi) // 2
        if minimum_detectable_effect(mid, sd, alpha, power) <= effect:
            hi = mid
        else:
            lo = mid + 1
    return lo


@dataclass
class SignTest:
    wins: int
    losses: int
    ties: int
    p: float


def sign_test(diffs: list[float]) -> SignTest:
    wins = sum(1 for d in diffs if d > 0)
    losses = sum(1 for d in diffs if d < 0)
    ties = len(diffs) - wins - losses
    n = wins + losses
    if n == 0:
        return SignTest(wins, losses, ties, 1.0)
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / 2**n
    return SignTest(wins, losses, ties, min(1.0, 2.0 * tail))


def cohen_kappa(a: list[str], b: list[str]) -> float:
    if len(a) != len(b) or not a:
        raise PrgError("kappa needs two label lists of the same non-zero length")
    n = len(a)
    labels = sorted(set(a) | set(b))
    observed = sum(1 for x, y in zip(a, b, strict=True) if x == y) / n
    expected = sum((a.count(lab) / n) * (b.count(lab) / n) for lab in labels)
    if expected == 1.0:
        return 1.0
    return (observed - expected) / (1.0 - expected)


def agreement_rate(a: list[str], b: list[str]) -> float:
    return sum(1 for x, y in zip(a, b, strict=True) if x == y) / len(a)


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(x: list[float], y: list[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        raise PrgError("spearman needs two lists of the same length, at least 2 long")
    rx, ry = _ranks(x), _ranks(y)
    mx, my = mean(rx), mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return 0.0 if den == 0 else num / den


def bootstrap_ci(diffs: list[float], reps: int, seed: int, alpha: float) -> tuple[float, float]:
    """Percentile interval of the mean, resampling with a seeded generator over a list (never a set)."""
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(mean(rng.choice(diffs) for _ in range(n)) for _ in range(reps))
    lo = means[int(math.floor(alpha / 2.0 * reps))]
    hi = means[min(reps - 1, int(math.ceil((1.0 - alpha / 2.0) * reps)) - 1)]
    return lo, hi
