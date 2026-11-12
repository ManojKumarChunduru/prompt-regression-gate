"""Experiment 1: the review census.

Scores per version and per reviewer, the reviewers' agreement with each other on which version
they prefer, and the observed effect per version pair on the canonical thirty and on the full
review. The spread between reviewers next to the spread between versions is the first screen's
argument: when they are the same size, thirty reviews cannot tell them apart.
"""

from collections import Counter
from statistics import mean, stdev

from lib import PAIRS, SETS, context, pct, table, write
from prg.gate import review_dimension, reviewer_agreement


def main() -> None:
    ctx = context()
    reviews = ctx.reviews
    versions = ctx.versions()
    per_version = {}
    for v in versions:
        scores = [r.score for r in reviews.rows if r.version == v]
        per_version[v] = {
            "mean": round(mean(scores), 3),
            "sd": round(stdev(scores), 3),
            "flagged": sum(1 for r in reviews.rows if r.version == v and r.flagged),
            "distribution": {str(k): n for k, n in sorted(Counter(scores).items())},
            "byReviewer": {
                rv: round(mean(r.score for r in reviews.rows if r.version == v and r.reviewer == rv), 3)
                for rv in reviews.reviewers
            },
        }
    # Spread between reviewers on the same summary, pooled over every summary.
    within = []
    for case_id in reviews.order:
        for v in versions:
            within.append(stdev(reviews.score(r, case_id, v) for r in reviews.reviewers))
    pairs = []
    for baseline, candidate in PAIRS:
        row = {"baseline": baseline, "candidate": candidate}
        for which in SETS:
            ids = reviews.reviewed_set(which)
            dim = review_dimension(ctx, baseline, candidate, ids, with_extras=False)
            agreement = reviewer_agreement(ctx, baseline, candidate, ids)
            row[which] = {
                "n": dim.n,
                "effect": round(dim.test.mean_diff, 4),
                "sd": round(dim.test.sd_diff, 4),
                "p": round(dim.test.p, 6),
                "direction": dim.direction,
                "agreementPct": agreement["meanAgreementPct"],
                "kappa": agreement["meanKappa"],
            }
        pairs.append(row)
    payload = {
        "cases": len(reviews.order),
        "reviewers": reviews.reviewers,
        "reviewRows": len(reviews.rows),
        "canonical": len(reviews.reviewed_set("first30")),
        "versions": per_version,
        "withinSummaryReviewerSpread": round(mean(within), 3),
        "pairs": pairs,
    }
    write("exp01_review_census", payload)
    print(
        table(
            [[v, d["mean"], d["sd"], d["flagged"]] for v, d in per_version.items()],
            ["version", "mean score", "sd", "flagged rows"],
        )
    )
    print(f"reviewer spread on one summary: {payload['withinSummaryReviewerSpread']}")
    print(
        table(
            [
                [
                    p["baseline"],
                    p["candidate"],
                    w,
                    p[w]["effect"],
                    p[w]["sd"],
                    p[w]["p"],
                    p[w]["direction"],
                    p[w]["agreementPct"],
                    p[w]["kappa"],
                ]
                for p in pairs
                for w in SETS
            ],
            ["baseline", "candidate", "set", "effect", "sd", "p", "direction", "agreement %", "kappa"],
        )
    )
    print(f"flagged share of rows: {pct(sum(d['flagged'] for d in per_version.values()), len(reviews.rows))}%")


if __name__ == "__main__":
    main()
