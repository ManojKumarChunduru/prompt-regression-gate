"""Experiment 4: the reviewer blind spot.

Bad claims in reviewed summaries that no reviewer flagged, the score given to summaries with a
contradicted claim against clean ones, and the rank correlation between review score and bad-claim
count. The uncomfortable one: the version reviewers prefer is the one with more unsupported claims,
and most of them were never flagged.
"""

from statistics import mean

from lib import context, pct, table, write
from prg.stats import spearman


def main() -> None:
    ctx = context()
    reviews = ctx.reviews
    rows = []
    pooled_scores, pooled_bad = [], []
    for v in ctx.versions():
        grounded = ctx.grounding(v)
        with_bad = [cid for cid, s in grounded.items() if s.bad > 0]
        flagged = [cid for cid in with_bad if reviews.flagged_by_any(cid, v)]
        unflagged_claims = sum(grounded[cid].bad for cid in with_bad if not reviews.flagged_by_any(cid, v))
        contradicted = [cid for cid, s in grounded.items() if s.count("contradicted") > 0]
        clean = [cid for cid, s in grounded.items() if s.bad == 0]
        scores = [reviews.case_mean(cid, v) for cid in grounded]
        bad = [grounded[cid].bad for cid in grounded]
        pooled_scores += scores
        pooled_bad += bad
        rows.append(
            {
                "version": v,
                "summariesWithABadClaim": len(with_bad),
                "flaggedByAnyReviewer": len(flagged),
                "unflaggedSummaries": len(with_bad) - len(flagged),
                "unflaggedPct": pct(len(with_bad) - len(flagged), len(with_bad)),
                "badClaimsTotal": sum(s.bad for s in grounded.values()),
                "badClaimsUnflagged": unflagged_claims,
                "meanScoreContradicted": round(mean(reviews.case_mean(cid, v) for cid in contradicted), 3)
                if contradicted
                else None,
                "meanScoreClean": round(mean(reviews.case_mean(cid, v) for cid in clean), 3) if clean else None,
                "meanScore": round(mean(scores), 3),
                "rankCorrelation": round(spearman(scores, [float(b) for b in bad]), 3),
            }
        )
    total_bad = sum(r["badClaimsTotal"] for r in rows)
    total_unflagged = sum(r["badClaimsUnflagged"] for r in rows)
    contradicted_all = [r["meanScoreContradicted"] for r in rows if r["meanScoreContradicted"] is not None]
    payload = {
        "versions": rows,
        "badClaimsTotal": total_bad,
        "badClaimsUnflagged": total_unflagged,
        "badClaimsUnflaggedPct": pct(total_unflagged, total_bad),
        "pooledRankCorrelation": round(spearman(pooled_scores, [float(b) for b in pooled_bad]), 3),
        "preferredVersion": max(rows, key=lambda r: r["meanScore"])["version"],
        "mostBadClaimsVersion": max(rows, key=lambda r: r["badClaimsTotal"])["version"],
        "meanScoreContradictedPooled": round(mean(contradicted_all), 3),
    }
    write("exp04_reviewer_blind_spot", payload)
    print(
        table(
            [
                [
                    r["version"],
                    r["summariesWithABadClaim"],
                    r["flaggedByAnyReviewer"],
                    f"{r['unflaggedPct']}%",
                    r["badClaimsUnflagged"],
                    r["meanScoreContradicted"],
                    r["meanScoreClean"],
                    r["rankCorrelation"],
                ]
                for r in rows
            ],
            [
                "version",
                "with a bad claim",
                "flagged by anyone",
                "unflagged",
                "unflagged bad claims",
                "score if contradicted",
                "score if clean",
                "rank corr",
            ],
        )
    )
    print(
        f"{total_unflagged} of {total_bad} bad claims unflagged ({payload['badClaimsUnflaggedPct']}%); reviewers prefer {payload['preferredVersion']}, most bad claims in {payload['mostBadClaimsVersion']}"
    )


if __name__ == "__main__":
    main()
