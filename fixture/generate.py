"""Writes the fixture: cases, comments, retrieved chunks, three versions of generations, three reviewers, and the planted truth.

Seeded (random.Random over lists only, so PYTHONHASHSEED cannot change the output), and a test
regenerates it under two hash seeds and compares byte for byte. The authored files in this
directory (README.md, policy/, force-app/, sfdx-project.json, broken/) are read, never written.

The planted truth in EXPECTED_VERDICTS.json is derived here, independently of the gate: the
faults the stand-in model applied are recorded as it applies them, and the expected gate verdicts
are computed with the statistics module and published t table values (2.045 at 29 degrees of
freedom, 1.972 at 199), not with the gate's own distribution code. Where the two disagree, the
truth is wrong first (tracker note 20) and the story is kept.

    python -I fixture/generate.py [--out DIR] [--seed N]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from prg.adapters import fixture as standin  # noqa: E402
from prg.exports import read_exports  # noqa: E402
from prg.generations import resolve, write_generation  # noqa: E402
from prg.metadata import find_template  # noqa: E402
from prg.policy import load_policy  # noqa: E402

SEED = 2026
CASES = 200
TEMPLATE_NAME = "Case_Summary"
T_CRIT = {29: 2.045, 199: 1.972}  # two-sided 0.05, from a published t table

PRODUCTS = {
    "Aero 2": [
        "stops charging after a few minutes",
        "overheats on the dock",
        "loses pairing every night",
        "shows a blank screen on boot",
    ],
    "Pulse Band": ["miscounts steps", "will not sync with the phone", "has a cracked strap clip", "drains in under a day"],
    "Nimbus Hub": [
        "drops the wifi hourly",
        "ignores the voice command",
        "reboots during updates",
        "flashes red and stays offline",
    ],
    "Strata Mini": [
        "prints streaks on every page",
        "jams the rear tray",
        "reports a false low-ink warning",
        "fails to wake from sleep",
    ],
    "Volt Charger": ["trips the breaker", "charges at half speed", "has a loose cable latch", "clicks and stops at 80 percent"],
    "Orbit Cam": ["records without audio", "misses motion at night", "fogs up in the rain", "logs out of the app daily"],
}
FIRST = [
    "Priya",
    "Daniel",
    "Mei",
    "Tomas",
    "Aisha",
    "Lukas",
    "Hannah",
    "Rohan",
    "Sofia",
    "Elias",
    "Nadia",
    "Marco",
    "Leila",
    "Owen",
    "Yara",
]
LAST = [
    "Natarajan",
    "Okafor",
    "Lindqvist",
    "Fernandes",
    "Haddad",
    "Novak",
    "Mbeki",
    "Sato",
    "Dubois",
    "Quintero",
    "Petrov",
    "Alvarez",
]
PRIORITIES = ["Low", "Medium", "High"]
STATUSES = ["New", "Working", "Escalated", "Closed"]
TYPES = ["Problem", "Question", "Feature Request"]
ORIGINS = ["Email", "Phone", "Web"]
ACTIONS = ["refund", "replacement", "credit", "repair"]
SECOND_ACTIONS = ["callback", "replacement", "cancellation", "refund"]
ARTICLES = {
    "Aero 2": [
        "Aero 2 units carry a 24-month warranty from the purchase date.",
        "Aero 2 firmware 3.2 fixes the charging fault on the dock.",
        "Returns of the Aero 2 need an RMA number within 30 days.",
    ],
    "Pulse Band": [
        "Pulse Band straps are replaced free within 12 months.",
        "Pulse Band syncs only over Bluetooth 5 or later.",
        "Pulse Band step counts are recalibrated after a 2-day wear period.",
    ],
    "Nimbus Hub": [
        "Nimbus Hub supports a 36-month extended warranty.",
        "Nimbus Hub reboots during updates when the 5-minute window is interrupted.",
        "Nimbus Hub needs a 2-hour cool-down before a factory reset.",
    ],
    "Strata Mini": [
        "Strata Mini cartridges are covered for 6 months.",
        "Strata Mini rear-tray jams clear with the 3-step reset.",
        "Strata Mini ink warnings reset after a 1-day idle period.",
    ],
    "Volt Charger": [
        "Volt Charger units are exchanged within 18 months for latch faults.",
        "Volt Charger limits output for 10 minutes when the breaker trips.",
        "Volt Charger stops at 80 percent for 2 hours on a hot day.",
    ],
    "Orbit Cam": [
        "Orbit Cam records audio only after a 1-hour first charge.",
        "Orbit Cam night mode needs the 3-month lens filter.",
        "Orbit Cam logs out after 7 days without a refresh.",
    ],
    "": [
        "Support hours are 24 hours a day for every product.",
        "A refund takes 10 days to reach the original card.",
        "Every exchange ships with a 14-day return label.",
    ],
}


def case_id(n: int) -> str:
    return f"500{n:012d}AAA"


def comment_id(n: int) -> str:
    return f"00a{n:012d}AAA"


def iso(day: dt.date) -> str:
    return day.isoformat()


def build_cases(rng: random.Random) -> tuple[list[dict], list[dict], list[dict], list[str]]:
    contacts = [f"{first} {last}" for first in FIRST for last in LAST]
    rng.shuffle(contacts)
    contacts = contacts[:60]
    cases, comments, chunks = [], [], []
    chunk_catalogue = [(product, index, text) for product, texts in ARTICLES.items() for index, text in enumerate(texts, start=1)]
    comment_counter = 1
    for n in range(1, CASES + 1):
        product = rng.choice(list(PRODUCTS))
        symptom = rng.choice(PRODUCTS[product])
        contact = rng.choice(contacts)
        opened = dt.date(2026, 1, 5) + dt.timedelta(days=rng.randint(0, 150))
        since = opened - dt.timedelta(days=rng.randint(1, 20))
        amount = rng.choice([49.0, 89.0, 120.0, 149.5, 199.0, 240.0, 310.0, 420.0, 575.0, 899.0])
        status = rng.choice(STATUSES)
        cid = case_id(n)
        cases.append(
            {
                "Id": cid,
                "CaseNumber": f"{n:08d}",
                "Subject": f"{product} {symptom}",
                "Description": f"Customer {contact} reports the {product} {symptom} since {iso(since)}.",
                "Priority": rng.choice(PRIORITIES),
                "Status": status,
                "Type": rng.choice(TYPES),
                "Origin": rng.choice(ORIGINS),
                "Product__c": product,
                "Contact.Name": contact,
                "Amount__c": f"{amount:.2f}",
                "CreatedDate": iso(opened),
                "ClosedDate": iso(opened + dt.timedelta(days=rng.randint(2, 30))) if status == "Closed" else "",
            }
        )
        day = opened
        bodies = [
            f"Confirmed with the customer: the {product} {symptom} since {iso(since)}. Serial SN-{rng.randint(10000, 99999)}."
        ]
        kind = rng.random()
        if kind < 0.6:
            bodies.append(f"Offered a {rng.choice(ACTIONS)} of ${amount:,.2f}.")
        elif kind < 0.8:
            bodies.append(f"Scheduled a callback on {iso(opened + dt.timedelta(days=rng.randint(1, 9)))}.")
        else:
            bodies.append(f"Escalated to tier 2 on {iso(opened + dt.timedelta(days=rng.randint(1, 5)))}.")
        if rng.random() < 0.6:
            bodies.append(
                f"Customer confirmed order ORD-{rng.randint(10000, 99999)} and asked for a {rng.choice(SECOND_ACTIONS)}."
            )
        if rng.random() < 0.3:
            bodies.append("Thanked the customer and set expectations for the next update.")
        for body in bodies:
            day = day + dt.timedelta(days=rng.randint(0, 3))
            comments.append(
                {
                    "Id": comment_id(comment_counter),
                    "ParentId": cid,
                    "CommentBody": body,
                    "CreatedDate": iso(day),
                    "CreatedBy.Name": "Support Agent",
                }
            )
            comment_counter += 1
        own = [c for c in chunk_catalogue if c[0] == product]
        general = [c for c in chunk_catalogue if c[0] == ""]
        others = [c for c in chunk_catalogue if c[0] not in ("", product)]
        picked = rng.sample(own, 2) + [rng.choice(general)]
        if rng.random() < 0.25:
            picked[rng.randrange(3)] = rng.choice(others)
        for rank, (cproduct, index, text) in enumerate(picked, start=1):
            slug = (cproduct or "general").lower().replace(" ", "-")
            chunks.append(
                {
                    "caseId": cid,
                    "rank": rank,
                    "chunkId": f"chunk-{slug}-{index:02d}",
                    "article": f"{cproduct or 'General'} support article",
                    "product": cproduct,
                    "text": text,
                    "score": round(0.95 - 0.07 * rank + rng.random() * 0.02, 4),
                }
            )
    return cases, comments, chunks, contacts


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in columns})


def review_score(rng: random.Random, model: dict, reviewer: str, fluency: float, omissions: int, bad: int) -> tuple[int, bool]:
    score = (
        model["base"]
        + fluency
        - model["omission_penalty"] * omissions
        + model["harshness"][reviewer]
        + rng.gauss(0.0, model["noise_sd"])
    )
    flagged = False
    if bad > 0 and rng.random() < model["flag_probability"] or bad == 0 and rng.random() < model["false_flag_probability"]:
        flagged = True
    if flagged:
        score -= model["flag_penalty"]
    return max(1, min(5, round(score))), flagged


def paired_direction(base: list[float], cand: list[float]) -> dict:
    diffs = [c - b for b, c in zip(base, cand, strict=True)]
    m, sd = statistics.mean(diffs), statistics.stdev(diffs)
    n = len(diffs)
    t = m / (sd / n**0.5) if sd else 0.0
    crit = T_CRIT[n - 1]
    direction = "undecided" if abs(t) < crit else ("better" if m > 0 else "worse")
    return {"n": n, "effect": round(m, 4), "sd": round(sd, 4), "t": round(t, 4), "critical": crit, "direction": direction}


def expected_exit(reviews: str, grounding: str) -> int:
    if reviews == "worse" or grounding == "worse":
        return 1
    if reviews == "undecided":
        return 2
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=HERE)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    out: Path = args.out
    rng = random.Random(args.seed)
    policy = load_policy(HERE / "policy" / "gate-policy.json")
    fault_model = json.loads((HERE / "policy" / "fault-model.json").read_text(encoding="utf-8"))
    template = find_template(HERE, policy.merge_field_families, TEMPLATE_NAME)

    cases, comments, chunks, contacts = build_cases(rng)
    data = out / "data"
    write_csv(data / "Case.csv", cases, list(cases[0].keys()))
    write_csv(data / "CaseComment.csv", comments, ["Id", "ParentId", "CommentBody", "CreatedDate", "CreatedBy.Name"])
    (data / "chunks.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks), encoding="utf-8")
    exports = read_exports(data)
    # The names a displaced contact can be drawn from are the names the export knows: a person the
    # org has never heard of is not an atom the grammar can see (ADR-002), so the first truth planted
    # contradictions the grounder could not grade.
    known_contacts = sorted({c["Contact.Name"] for c in cases})

    versions = list(template.versions)
    faults: dict[str, dict[str, list[dict]]] = {v: {} for v in versions}
    for identifier in versions:
        version = template.version(identifier)
        model = dict(fault_model["versions"][identifier])
        model["invented_templates"] = fault_model["invented_sentences"]["templates"]
        for case in cases:
            cid = case["Id"]
            vrng = random.Random(f"{args.seed}:{identifier}:{cid}")
            text, planted = standin.generate(exports.case(cid), version, vrng, model, known_contacts)
            prompt = resolve(version, exports.case(cid), exports, policy)
            request_id = f"req-{identifier}-{cid[-6:-3]}"
            write_generation(
                out / "generations" / identifier / f"{cid}.json", TEMPLATE_NAME, identifier, cid, text, prompt, request_id
            )
            faults[identifier][cid] = [
                {"kind": p.kind, "atomKind": p.atom_kind, "atom": p.atom, "displaced": p.displaced, "sentence": p.sentence}
                for p in planted
            ]

    order = [c["Id"] for c in cases]
    random.Random(f"{args.seed}:order").shuffle(order)
    reviews_dir = out / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    (reviews_dir / "order.txt").write_text("\n".join(order) + "\n", encoding="utf-8")
    reviewer_model = fault_model["reviewers"]
    scores: dict[tuple[str, str, str], int] = {}
    for reviewer in reviewer_model["harshness"]:
        rows = []
        for cid in order:
            for identifier in versions:
                planted = faults[identifier][cid]
                omissions = sum(1 for p in planted if p["kind"] == "omission")
                bad = sum(1 for p in planted if p["kind"] in ("unsupported", "contradicted", "misgrounded"))
                rrng = random.Random(f"{args.seed}:{reviewer}:{cid}:{identifier}")
                score, flagged = review_score(
                    rrng, reviewer_model, reviewer, fault_model["versions"][identifier]["fluency"], omissions, bad
                )
                scores[(reviewer, cid, identifier)] = score
                rows.append(
                    {
                        "caseId": cid,
                        "version": identifier,
                        "score": score,
                        "flagged": "yes" if flagged else "no",
                        "note": "flagged a claim the case does not support" if flagged else "",
                    }
                )
        write_csv(reviews_dir / f"{reviewer}.csv", rows, ["caseId", "version", "score", "flagged", "note"])

    reviewers = list(reviewer_model["harshness"])

    def case_mean(cid: str, identifier: str) -> float:
        return statistics.mean(scores[(r, cid, identifier)] for r in reviewers)

    def bad_count(cid: str, identifier: str) -> float:
        return float(sum(1 for p in faults[identifier][cid] if p["kind"] in ("unsupported", "contradicted", "misgrounded")))

    verdicts = []
    for baseline in versions:
        for candidate in versions:
            if baseline == candidate:
                continue
            grounding = paired_direction([-bad_count(c, baseline) for c in order], [-bad_count(c, candidate) for c in order])
            for which, ids in (("first30", order[:30]), ("all", order)):
                reviews = paired_direction([case_mean(c, baseline) for c in ids], [case_mean(c, candidate) for c in ids])
                verdicts.append(
                    {
                        "baseline": baseline,
                        "candidate": candidate,
                        "reviewedSet": which,
                        "reviews": reviews,
                        "grounding": grounding,
                        "exitCode": expected_exit(reviews["direction"], grounding["direction"]),
                    }
                )

    by_version = {}
    for identifier in versions:
        kinds = {k: 0 for k in ("unsupported", "contradicted", "misgrounded", "unverifiable", "omission")}
        for planted in faults[identifier].values():
            for p in planted:
                kinds[p["kind"]] += 1
        by_version[identifier] = kinds
    truth = {
        "note": "planted by fixture/generate.py; every fault the stand-in model applied, and the gate verdicts derived with the statistics module and published t table values",
        "seed": args.seed,
        "cases": len(cases),
        "comments": len(comments),
        "chunks": len(chunks),
        "versions": versions,
        "reviewers": reviewers,
        "canonicalThirty": order[:30],
        "faultsByVersion": by_version,
        "faults": faults,
        "verdicts": verdicts,
    }
    (out / "EXPECTED_VERDICTS.json").write_text(json.dumps(truth, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    bad_total = sum(
        sum(v for k, v in kinds.items() if k in ("unsupported", "contradicted", "misgrounded")) for kinds in by_version.values()
    )
    print(
        f"generate: {len(cases)} cases, {len(comments)} comments, {len(chunks)} chunks, {len(versions)} versions, {bad_total} planted bad claims, {len(verdicts)} verdicts"
    )
    for v in verdicts:
        print(
            f"  {v['baseline']} -> {v['candidate']} {v['reviewedSet']:8} reviews {v['reviews']['direction']:9} ({v['reviews']['effect']:+.3f}, t {v['reviews']['t']:+.2f}) grounding {v['grounding']['direction']:9} ({v['grounding']['effect']:+.3f}) exit {v['exitCode']}"
        )


if __name__ == "__main__":
    main()
