"""Loads everything once and applies the gate to one prompt change.

Two dimensions, the same arithmetic. The review dimension pairs the candidate against the
baseline per reviewed case on the mean of the reviewers; the grounding dimension pairs them per
generated case on the count of bad claims, over every generation and not only the reviewed set.
Each dimension is better, worse or undecided at the policy's alpha. The verdict: blocked when
either is worse; ship when the reviews are better and the grounding is not worse; cannot decide
otherwise. A version whose contract names a field the export lacks has its grounding refused,
which is a cannot-decide on its own (ADR-004).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path

from . import stats
from .claims import Grammar, load_grammar
from .exit_codes import BLOCKED, SHIP, UNDECIDED, PrgError
from .exports import Exports, read_exports
from .generations import Generation, check_prompts, read_generations
from .grounding import GroundedSummary, census, ground_version, vocabularies
from .metadata import Template, find_template
from .policy import Policy, load_policy
from .reviews import Reviews, read_reviews


@dataclass
class Context:
    project_dir: Path
    data_dir: Path
    generations_dir: Path
    reviews_dir: Path | None
    policy: Policy
    grammar: Grammar
    template: Template
    exports: Exports
    vocab: dict[str, list[str]]
    generations: dict[str, dict[str, Generation]] = field(default_factory=dict)
    grounded: dict[str, dict[str, GroundedSummary]] = field(default_factory=dict)
    refused: dict[str, str] = field(default_factory=dict)  # version -> reason grounding was refused
    reviews: Reviews | None = None

    def versions(self) -> list[str]:
        return list(self.template.versions)

    def grounding(self, version: str) -> dict[str, GroundedSummary]:
        if version in self.refused:
            raise PrgError(f"version {version}: grounding refused ({self.refused[version]})")
        if version not in self.grounded:
            raise PrgError(f"version {version}: no generations loaded")
        return self.grounded[version]


def load_context(
    project_dir: Path,
    data_dir: Path,
    generations_dir: Path,
    reviews_dir: Path | None,
    policy_path: Path | None,
    grammar_path: Path,
    template_name: str | None = None,
    versions: list[str] | None = None,
) -> Context:
    policy = load_policy(policy_path)
    grammar = load_grammar(grammar_path)
    template = find_template(Path(project_dir), policy.merge_field_families, template_name)
    exports = read_exports(Path(data_dir))
    ctx = Context(
        Path(project_dir),
        Path(data_dir),
        Path(generations_dir),
        reviews_dir,
        policy,
        grammar,
        template,
        exports,
        vocabularies(exports),
    )
    wanted = versions or list(template.versions)
    for identifier in wanted:
        version = template.version(identifier)
        folder = Path(generations_dir) / identifier
        if not folder.exists():
            continue
        gens = read_generations(Path(generations_dir), identifier)
        ctx.generations[identifier] = gens
        try:
            drifted = check_prompts(version, gens, exports, policy)
        except PrgError as exc:
            ctx.refused[identifier] = str(exc)
            continue
        if drifted:
            raise PrgError(
                f"version {identifier}: {len(drifted)} committed prompts differ from the resolved template "
                f"(first: {drifted[0]}); the contract and the generations drifted apart"
            )
        ctx.grounded[identifier] = ground_version(gens, version, exports, grammar, ctx.vocab)
    if reviews_dir is not None and Path(reviews_dir).exists():
        ctx.reviews = read_reviews(Path(reviews_dir), policy, versions=list(ctx.generations) or None)
    return ctx


@dataclass
class Dimension:
    name: str
    n: int
    test: stats.PairedTest | None
    direction: str  # better, worse, undecided, refused
    floor: float | None  # minimum detectable effect at n
    min_n: int | None  # minimum n for the observed effect
    baseline_mean: float
    candidate_mean: float
    refusal: str = ""
    sign: stats.SignTest | None = None
    bootstrap: tuple[float, float] | None = None

    def as_dict(self) -> dict:
        t = self.test
        return {
            "name": self.name,
            "n": self.n,
            "direction": self.direction,
            "baselineMean": round(self.baseline_mean, 4),
            "candidateMean": round(self.candidate_mean, 4),
            "effect": round(t.mean_diff, 4) if t else None,
            "sd": round(t.sd_diff, 4) if t else None,
            "t": round(t.t, 4) if t else None,
            "df": t.df if t else None,
            "p": round(t.p, 6) if t else None,
            "ciLow": round(t.ci_low, 4) if t else None,
            "ciHigh": round(t.ci_high, 4) if t else None,
            "floor": round(self.floor, 4) if self.floor is not None else None,
            "minN": self.min_n,
            "sign": {"wins": self.sign.wins, "losses": self.sign.losses, "ties": self.sign.ties, "p": round(self.sign.p, 6)}
            if self.sign
            else None,
            "bootstrapLow": round(self.bootstrap[0], 4) if self.bootstrap else None,
            "bootstrapHigh": round(self.bootstrap[1], 4) if self.bootstrap else None,
            "refusal": self.refusal,
        }


@dataclass
class GateResult:
    baseline: str
    candidate: str
    reviewed_set: str
    reviews: Dimension
    grounding: Dimension
    exit_code: int
    reasons: list[str]

    def as_dict(self) -> dict:
        return {
            "baseline": self.baseline,
            "candidate": self.candidate,
            "reviewedSet": self.reviewed_set,
            "reviews": self.reviews.as_dict(),
            "grounding": self.grounding.as_dict(),
            "exitCode": self.exit_code,
            "reasons": self.reasons,
        }


def _dimension(name: str, base: list[float], cand: list[float], policy: Policy, with_extras: bool) -> Dimension:
    diffs = [c - b for b, c in zip(base, cand, strict=True)]
    test = stats.paired_t(diffs, policy.alpha)
    floor = stats.minimum_detectable_effect(test.n, test.sd_diff, policy.alpha, policy.power) if test.sd_diff > 0 else 0.0
    min_n = stats.minimum_n(test.mean_diff, test.sd_diff, policy.alpha, policy.power)
    sign = stats.sign_test(diffs) if with_extras else None
    boot = stats.bootstrap_ci(diffs, policy.bootstrap_reps, policy.bootstrap_seed, policy.alpha) if with_extras else None
    return Dimension(name, test.n, test, test.direction, floor, min_n, stats.mean(base), stats.mean(cand), "", sign, boot)


def review_dimension(ctx: Context, baseline: str, candidate: str, case_ids: list[str], with_extras: bool = True) -> Dimension:
    if ctx.reviews is None:
        return Dimension("reviews", 0, None, "refused", None, None, 0.0, 0.0, "no reviews directory")
    base = [ctx.reviews.case_mean(c, baseline) for c in case_ids]
    cand = [ctx.reviews.case_mean(c, candidate) for c in case_ids]
    return _dimension("reviews", base, cand, ctx.policy, with_extras)


def grounding_dimension(ctx: Context, baseline: str, candidate: str, with_extras: bool = True) -> Dimension:
    for v in (baseline, candidate):
        if v in ctx.refused:
            return Dimension("grounding", 0, None, "refused", None, None, 0.0, 0.0, f"version {v}: {ctx.refused[v]}")
        if v not in ctx.grounded:
            return Dimension("grounding", 0, None, "refused", None, None, 0.0, 0.0, f"version {v}: no generations")
    base_g, cand_g = ctx.grounded[baseline], ctx.grounded[candidate]
    case_ids = [c for c in base_g if c in cand_g]
    if len(case_ids) < 3:
        return Dimension(
            "grounding", len(case_ids), None, "refused", None, None, 0.0, 0.0, "fewer than 3 cases generated for both versions"
        )
    # Bad claims per case; the candidate is better when it has fewer, so the diff is negated to keep
    # "better" meaning a positive effect, as for the reviews.
    base = [float(-base_g[c].bad) for c in case_ids]
    cand = [float(-cand_g[c].bad) for c in case_ids]
    dim = _dimension("grounding", base, cand, ctx.policy, with_extras)
    dim.baseline_mean, dim.candidate_mean = -dim.baseline_mean, -dim.candidate_mean
    return dim


def decide(reviews: Dimension, grounding: Dimension) -> tuple[int, list[str]]:
    reasons: list[str] = []
    if reviews.direction == "worse":
        reasons.append(
            f"reviews: the candidate scores lower by {abs(reviews.test.mean_diff):.3f}, beyond the floor (p {reviews.test.p:.4f})"
        )
    if grounding.direction == "worse":
        reasons.append(
            f"grounding: the candidate carries more bad claims by {abs(grounding.test.mean_diff):.3f} per case "
            f"(p {grounding.test.p:.4f})"
        )
    if reasons:
        return BLOCKED, reasons
    if reviews.direction == "refused":
        reasons.append(f"reviews: {reviews.refusal}")
    if grounding.direction == "refused":
        reasons.append(f"grounding: {grounding.refusal}")
    if reviews.direction == "undecided":
        n_text = f"{reviews.min_n} reviews" if reviews.min_n else "no finite number of reviews (the observed effect is zero)"
        reasons.append(
            f"reviews: ahead by {reviews.test.mean_diff:.3f} on {reviews.n}, below the floor of {reviews.floor:.3f}; "
            f"the observed effect would need {n_text}"
        )
    if reasons:
        return UNDECIDED, reasons
    if grounding.direction == "undecided":
        reasons.append(
            f"grounding: not demonstrably different ({grounding.test.mean_diff:+.3f} bad claims per case, "
            f"p {grounding.test.p:.4f})"
        )
    reasons.insert(
        0,
        f"reviews: ahead by {reviews.test.mean_diff:.3f} on {reviews.n}, beyond the floor of {reviews.floor:.3f} "
        f"(p {reviews.test.p:.4f})",
    )
    return SHIP, reasons


def run_gate(ctx: Context, baseline: str, candidate: str, reviewed_set: str | None = None) -> GateResult:
    if baseline == candidate:
        raise PrgError("baseline and candidate are the same version")
    for v in (baseline, candidate):
        ctx.template.version(v)
    which = reviewed_set or ctx.policy.reviewed_set
    if ctx.reviews is None:
        reviews = Dimension("reviews", 0, None, "refused", None, None, 0.0, 0.0, "no reviews directory")
    else:
        case_ids = ctx.reviews.reviewed_set(which)
        reviews = review_dimension(ctx, baseline, candidate, case_ids)
    grounding = grounding_dimension(ctx, baseline, candidate)
    code, reasons = decide(reviews, grounding)
    return GateResult(baseline, candidate, which, reviews, grounding, code, reasons)


# The arithmetic beyond one verdict: the prefix sweep and the draws (experiment 2, `prg power`).


def prefix_sweep(ctx: Context, baseline: str, candidate: str, start: int = 10) -> list[dict]:
    """The review dimension at every prefix of the committed order from `start` to all."""
    assert ctx.reviews is not None
    order = ctx.reviews.order
    rows = []
    for n in range(start, len(order) + 1):
        dim = review_dimension(ctx, baseline, candidate, order[:n], with_extras=False)
        rows.append(
            {
                "n": n,
                "effect": round(dim.test.mean_diff, 4),
                "p": round(dim.test.p, 6),
                "floor": round(dim.floor, 4),
                "direction": dim.direction,
            }
        )
    return rows


def first_clearing_n(sweep: list[dict]) -> int | None:
    for row in sweep:
        if row["direction"] == "better":
            return row["n"]
    return None


def draws(ctx: Context, baseline: str, candidate: str) -> dict:
    """Thirties (the policy's size) drawn from the full review, seeded, over a list."""
    assert ctx.reviews is not None
    rng = random.Random(ctx.policy.draws_seed)
    order = list(ctx.reviews.order)
    clear = wrong = worse = 0
    effects = []
    for _ in range(ctx.policy.draws_count):
        sample = rng.sample(order, ctx.policy.draws_size)
        dim = review_dimension(ctx, baseline, candidate, sample, with_extras=False)
        effects.append(dim.test.mean_diff)
        if dim.direction == "better":
            clear += 1
        if dim.direction == "worse":
            worse += 1
        if dim.test.mean_diff < 0:
            wrong += 1
    return {
        "count": ctx.policy.draws_count,
        "size": ctx.policy.draws_size,
        "seed": ctx.policy.draws_seed,
        "clearAlpha": clear,
        "clearAlphaPct": round(100.0 * clear / ctx.policy.draws_count, 1),
        "wrongWay": wrong,
        "wrongWayPct": round(100.0 * wrong / ctx.policy.draws_count, 1),
        "decidedWorse": worse,
        "effectMin": round(min(effects), 4),
        "effectMax": round(max(effects), 4),
    }


def reviewer_agreement(ctx: Context, baseline: str, candidate: str, case_ids: list[str]) -> dict:
    assert ctx.reviews is not None
    reviewers = ctx.reviews.reviewers
    prefs = {r: ctx.reviews.preferences(r, baseline, candidate, case_ids) for r in reviewers}
    pairs = []
    for i, a in enumerate(reviewers):
        for b in reviewers[i + 1 :]:
            pairs.append(
                {
                    "a": a,
                    "b": b,
                    "agreement": stats.agreement_rate(prefs[a], prefs[b]),
                    "kappa": stats.cohen_kappa(prefs[a], prefs[b]),
                }
            )
    return {
        "pairs": [{**p, "agreement": round(p["agreement"], 4), "kappa": round(p["kappa"], 4)} for p in pairs],
        "meanAgreementPct": round(100.0 * stats.mean(p["agreement"] for p in pairs), 1),
        "meanKappa": round(stats.mean(p["kappa"] for p in pairs), 3),
    }


def grounding_census(ctx: Context, version: str) -> dict:
    return census(ctx.grounding(version))
