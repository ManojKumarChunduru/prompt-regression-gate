"""Experiment 3: the grounding census.

Claims per version by verdict and by first supporting source, mis-grounded claims on the retriever
version, bad claims per case, and recall against the planted faults with the resolution floor:
the number the review score cannot see.
"""

from statistics import mean

from lib import context, pct, table, truth, write
from prg.gate import grounding_census

BAD = ("unsupported", "contradicted", "misgrounded")


def main() -> None:
    ctx = context()
    planted = truth()
    versions = {}
    recall = {"planted": 0, "recovered": 0, "falsePositives": 0, "byKind": {}}
    for v in ctx.versions():
        grounded = ctx.grounding(v)
        c = grounding_census(ctx, v)
        c["badPerCase"] = round(mean(s.bad for s in grounded.values()), 4)
        c["summariesWithABadClaim"] = sum(1 for s in grounded.values() if s.bad > 0)
        c["unverifiablePct"] = pct(c["unverifiable"], c["claims"])
        versions[v] = c
        for case_id, faults in planted["faults"][v].items():
            verdicts = {cl.text: cl.verdict for cl in grounded[case_id].claims}
            planted_bad = {f["sentence"]: f["kind"] for f in faults if f["kind"] in BAD}
            for sentence, kind in planted_bad.items():
                recall["planted"] += 1
                recall["byKind"].setdefault(kind, {"planted": 0, "recovered": 0})
                recall["byKind"][kind]["planted"] += 1
                if verdicts.get(sentence) == kind:
                    recall["recovered"] += 1
                    recall["byKind"][kind]["recovered"] += 1
            for sentence, verdict in verdicts.items():
                if verdict in BAD and sentence not in planted_bad:
                    recall["falsePositives"] += 1
    recall["falseNegatives"] = recall["planted"] - recall["recovered"]
    recall["floor"] = recall["planted"]
    totals = {
        "claims": sum(c["claims"] for c in versions.values()),
        "bad": sum(c["bad"] for c in versions.values()),
        "unverifiable": sum(c["unverifiable"] for c in versions.values()),
        "summaries": sum(c["summaries"] for c in versions.values()),
    }
    totals["unverifiablePct"] = pct(totals["unverifiable"], totals["claims"])
    totals["badPct"] = pct(totals["bad"], totals["claims"] - totals["unverifiable"])
    payload = {"versions": versions, "recall": recall, "totals": totals}
    write("exp03_grounding_census", payload)
    print(
        table(
            [
                [
                    v,
                    c["claims"],
                    c["supported"],
                    c["unsupported"],
                    c["contradicted"],
                    c["misgrounded"],
                    c["unverifiable"],
                    c["badPerCase"],
                    c["summariesWithABadClaim"],
                ]
                for v, c in versions.items()
            ],
            [
                "version",
                "claims",
                "supported",
                "unsupported",
                "contradicted",
                "mis-grounded",
                "unverifiable",
                "bad per case",
                "summaries with a bad claim",
            ],
        )
    )
    print(
        f"recall: {recall['recovered']} of {recall['planted']} planted faults, {recall['falsePositives']} false positives, floor 1 in {recall['floor']}"
    )


if __name__ == "__main__":
    main()
