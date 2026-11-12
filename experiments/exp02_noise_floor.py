"""Experiment 2: the noise floor.

For each version pair: the paired t and its p, the sign test, the interval, the minimum detectable
effect at thirty (the floor), the minimum n for the observed effect by the formula and the n at
which the gate actually clears along the committed order; and five hundred seeded draws of thirty
from the full review: the share that clears alpha and the share that points the wrong way. The
headline.
"""

from lib import PAIRS, context, table, write
from prg.gate import draws, first_clearing_n, prefix_sweep, review_dimension


def main() -> None:
    ctx = context()
    reviews = ctx.reviews
    rows = []
    for baseline, candidate in PAIRS:
        thirty = review_dimension(ctx, baseline, candidate, reviews.reviewed_set("first30"))
        full = review_dimension(ctx, baseline, candidate, reviews.reviewed_set("all"))
        sweep = prefix_sweep(ctx, baseline, candidate)
        clears = first_clearing_n(sweep)
        d = draws(ctx, baseline, candidate)
        rows.append(
            {
                "baseline": baseline,
                "candidate": candidate,
                "thirty": {**thirty.as_dict(), "n": thirty.n},
                "full": {**full.as_dict(), "n": full.n},
                "clearsAt": clears,
                "formulaMinusMeasured": (thirty.min_n - clears) if (thirty.min_n is not None and clears is not None) else None,
                "sweep": sweep,
                "draws": d,
            }
        )
    payload = {"alpha": ctx.policy.alpha, "power": ctx.policy.power, "pairs": rows}
    write("exp02_noise_floor", payload)
    print(
        table(
            [
                [
                    r["baseline"],
                    r["candidate"],
                    r["thirty"]["effect"],
                    r["thirty"]["floor"],
                    r["thirty"]["p"],
                    r["thirty"]["minN"],
                    r["clearsAt"],
                    r["full"]["effect"],
                    r["full"]["p"],
                    f"{r['draws']['clearAlphaPct']}%",
                    f"{r['draws']['wrongWayPct']}%",
                ]
                for r in rows
            ],
            [
                "baseline",
                "candidate",
                "effect @30",
                "floor @30",
                "p @30",
                "n by formula",
                "clears at",
                "effect @200",
                "p @200",
                "thirties clearing",
                "wrong way",
            ],
        )
    )


if __name__ == "__main__":
    main()
