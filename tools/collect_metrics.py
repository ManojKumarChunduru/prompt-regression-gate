"""Re-measures every published figure and writes docs/metrics.json.

Nothing here is typed by hand: the test count comes from the junit report, the coverage from
coverage.py's JSON, everything else from the experiment JSON that `make experiments` wrote. The
anchor phrases beside each metric are the exact wording a document must use; tools/check_numbers.py
enforces them. Before writing, the stems are checked against each other, so a collision fails here
and never as a false STALE on correct prose.

Run through `make receipts` (which runs coverage and the experiments first).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def fail(message: str) -> None:
    print(f"collect_metrics: {message}", file=sys.stderr)
    sys.exit(1)


def read(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


junit_path = ROOT / "docs" / "test-results.xml"
if not junit_path.exists():
    fail("docs/test-results.xml is missing; run `make coverage` first")
tests_total = len(re.findall(r"<testcase ", junit_path.read_text(encoding="utf-8")))
if tests_total == 0:
    fail("no testcase elements in docs/test-results.xml")

coverage_path = ROOT / "coverage.json"
if not coverage_path.exists():
    fail("coverage.json is missing; run `make coverage` first")
coverage_pct = read("coverage.json")["totals"]["percent_covered"]

exp1 = read("docs/experiments/exp01_review_census.json")
exp2 = read("docs/experiments/exp02_noise_floor.json")
exp3 = read("docs/experiments/exp03_grounding_census.json")
exp4 = read("docs/experiments/exp04_reviewer_blind_spot.json")
exp5 = read("docs/experiments/exp05_gate_matrix.json")


def one(n: float) -> str:
    return str(round(float(n), 1))


def three(n: float) -> str:
    return f"{abs(float(n)):.3f}"


metrics: dict[str, object] = {}
anchors: dict[str, list[str]] = {}


def add(key: str, value: object, phrases: list[str]) -> None:
    if key in metrics:
        fail(f"metric {key} defined twice")
    metrics[key] = value
    anchors[key] = phrases


add("tests_total", tests_total, ["{} tests"])
add("coverage_line_pct", one(coverage_pct), ["{}% line coverage"])

# The fixture's shape.
add("cases_total", exp1["cases"], ["{} cases in the fixture", "{} fixture cases"])
truth = read("fixture/EXPECTED_VERDICTS.json")
add("comments_total", truth["comments"], ["{} case comments"])
add("chunks_total", truth["chunks"], ["{} retrieved chunks"])
add("versions_total", len(truth["versions"]), ["{} template versions"])
add("generations_total", exp3["totals"]["summaries"], ["{} generated summaries"])
add("reviewers_total", len(exp1["reviewers"]), ["{} reviewers"])
add("review_rows_total", exp1["reviewRows"], ["{} review rows"])
add("canonical_cases", exp1["canonical"], ["canonical set of {} cases"])
add("reviewer_spread", three(exp1["withinSummaryReviewerSpread"]), ["{} points between reviewers on one summary"])
add("flagged_rows", sum(v["flagged"] for v in exp1["versions"].values()), ["{} flagged review rows"])
add(
    "flagged_rows_pct",
    one(100 * sum(v["flagged"] for v in exp1["versions"].values()) / exp1["reviewRows"]),
    ["{}% of review rows flagged"],
)
for v, d in exp1["versions"].items():
    add(f"mean_score_{v}", three(d["mean"]), [f"{v} averages {{}}"])

# The noise floor, per pair. Names: the fluent rewrite (v1 to v2), the careful rewrite (v1 to v3), v3 against v2.
NAMES = {("v1", "v2"): "fluent", ("v1", "v3"): "careful", ("v2", "v3"): "sibling"}
PROSE = {"fluent": "fluent rewrite", "careful": "careful rewrite", "sibling": "v3 against v2"}
for pair in exp2["pairs"]:
    name = NAMES[(pair["baseline"], pair["candidate"])]
    who = PROSE[name]
    t, full, d = pair["thirty"], pair["full"], pair["draws"]
    verb30 = "ahead by" if t["effect"] >= 0 else "trails by"
    verb_all = "ahead by" if full["effect"] >= 0 else "trails by"
    add(f"{name}_effect_30", three(t["effect"]), [f"{who} {verb30} {{}} on thirty"])
    add(f"{name}_floor_30", three(t["floor"]), [f"{name} floor of {{}}"])
    add(f"{name}_sd_30", three(t["sd"]), [f"{name} paired spread of {{}}"])
    add(f"{name}_p_30", three(t["p"]), [f"{name} p of {{}} on thirty"])
    add(f"{name}_effect_all", three(full["effect"]), [f"{who} {verb_all} {{}} on the full review"])
    add(f"{name}_p_all", f"{full['p']:.5f}" if full["p"] < 0.001 else three(full["p"]), [f"{name} p of {{}} on the full review"])
    add(f"{name}_draws_clear_pct", one(d["clearAlphaPct"]), [f"{{}}% of {who} thirties clear"])
    add(f"{name}_draws_wrong_pct", one(d["wrongWayPct"]), [f"{{}}% of {who} thirties point the wrong way"])
    add(
        f"{name}_sign_wins",
        t["sign"]["wins"],
        [f"{name} sign test {{}} wins, {{m:{name}_sign_losses}} losses, {{m:{name}_sign_ties}} ties"],
    )
    add(
        f"{name}_sign_losses",
        t["sign"]["losses"],
        [f"{name} sign test {{m:{name}_sign_wins}} wins, {{}} losses, {{m:{name}_sign_ties}} ties"],
    )
    add(
        f"{name}_sign_ties",
        t["sign"]["ties"],
        [f"{name} sign test {{m:{name}_sign_wins}} wins, {{m:{name}_sign_losses}} losses, {{}} ties"],
    )
    if t["minN"] is not None:
        add(f"{name}_min_n", t["minN"], [f"{name} formula says {{}} reviews"])
    if pair["clearsAt"] is not None:
        add(f"{name}_clears_at", pair["clearsAt"], [f"{who} clears at {{}} reviews"])
    if name == "careful":
        add("careful_ci_low_abs", three(t["ciLow"]), ["careful interval from minus {} to {m:careful_ci_high}"])
        add("careful_ci_high", three(t["ciHigh"]), ["careful interval from minus {m:careful_ci_low_abs} to {}"])
    if name == "fluent":
        add("fluent_ci_low", three(t["ciLow"]), ["fluent interval from {} to {m:fluent_ci_high}"])
        add("fluent_ci_high", three(t["ciHigh"]), ["fluent interval from {m:fluent_ci_low} to {}"])
add("draws_count", exp2["pairs"][0]["draws"]["count"], ["{} draws of thirty"])
careful_30 = next(p for p in exp1["pairs"] if (p["baseline"], p["candidate"]) == ("v1", "v3"))["first30"]
add("careful_agreement_pct", one(careful_30["agreementPct"]), ["{}% pairwise reviewer agreement"])
add("careful_kappa", three(careful_30["kappa"]), ["mean kappa of {}"])

# The grounding census.
add("claims_total", exp3["totals"]["claims"], ["{} claims extracted"])
add("bad_total", exp3["totals"]["bad"], ["{} bad claims in all"])
add("bad_pct", one(exp3["totals"]["badPct"]), ["{}% of checkable claims are bad"])
add("unverifiable_total", exp3["totals"]["unverifiable"], ["{} unverifiable claims"])
add("unverifiable_pct", one(exp3["totals"]["unverifiablePct"]), ["{}% of claims unverifiable"])
for v, c in exp3["versions"].items():
    add(f"claims_{v}", c["claims"], [f"{{}} {v} claims"])
    add(f"supported_{v}", c["supported"], [f"{{}} supported in {v}"])
    add(f"unsupported_{v}", c["unsupported"], [f"{{}} unsupported in {v}"])
    add(f"contradicted_{v}", c["contradicted"], [f"{{}} contradicted in {v}"])
    add(f"unverifiable_{v}", c["unverifiable"], [f"{{}} unverifiable in {v}"])
    add(f"bad_{v}", c["bad"], [f"{{}} bad claims in {v}"])
    add(f"bad_per_case_{v}", three(c["badPerCase"]), [f"{{}} bad claims per {v} case"])
    add(f"summaries_with_bad_{v}", c["summariesWithABadClaim"], [f"{{}} {v} summaries carry a bad claim"])
add("misgrounded_v3", exp3["versions"]["v3"]["misgrounded"], ["{} mis-grounded through a chunk"])
recall = exp3["recall"]
add("planted_faults", recall["planted"], ["{} planted faults", "floor 1 in {}"])
add("faults_recovered", recall["recovered"], ["{} of {m:planted_faults} faults recovered"])
add("false_positives", recall["falsePositives"], ["{} false positives"])
add("false_negatives", recall["falseNegatives"], ["{} false negatives"])
for kind, r in recall["byKind"].items():
    add(f"planted_{kind}", r["planted"], [f"{{}} planted {kind}"])
# The grounding dimension per pair, from the gate matrix.
rows = {(r["baseline"], r["candidate"], r["reviewedSet"]): r for r in exp5["rows"]}
add("fluent_grounding_effect", three(rows[("v1", "v2", "all")]["groundingEffect"]), ["{} more bad claims per case than v1"])
add("careful_grounding_effect", three(rows[("v1", "v3", "all")]["groundingEffect"]), ["{} bad claims per case apart from v1"])
add("sibling_grounding_effect", three(rows[("v2", "v3", "all")]["groundingEffect"]), ["{} fewer bad claims per case than v2"])

# The reviewer blind spot.
add("unflagged_bad_claims", exp4["badClaimsUnflagged"], ["{} bad claims no reviewer flagged"])
add("unflagged_bad_pct", one(exp4["badClaimsUnflaggedPct"]), ["{}% of bad claims unflagged"])
for r in exp4["versions"]:
    v = r["version"]
    add(f"unflagged_summaries_pct_{v}", one(r["unflaggedPct"]), [f"{{}}% of {v} summaries with a bad claim went unflagged"])
    add(f"score_contradicted_{v}", three(r["meanScoreContradicted"]), [f"{v} summaries with a contradicted claim score {{}}"])
    add(f"score_clean_{v}", three(r["meanScoreClean"]), [f"clean {v} summaries score {{}}"])
add("pooled_rank_corr_abs", three(exp4["pooledRankCorrelation"]), ["rank correlation of minus {}"])

# The gate matrix.
add("matrix_rows", len(exp5["rows"]), ["{} gate rows"])
for code, count in exp5["exitCounts"].items():
    add(f"matrix_exit_{code}", count, [f"{{}} rows exit {code}"])
add("regression_wins_rows", exp5["regressionWinsRows"], ["{} rows where a regression wins"])
add("forbidden_on_default_path", exp5["defaultPathForbiddenCount"], ["{} forbidden modules on the default path"])
for r in exp5["rows"]:
    key = f"{r['baseline']}_{r['candidate']}_{r['reviewedSet']}"
    rs = "+" if r["reviewsEffect"] >= 0 else "-"
    gs = "+" if r["groundingEffect"] >= 0 else "-"
    prefix = f"| {r['baseline']} | {r['candidate']} | {r['reviewedSet']} | {r['reviews']} | "
    add(
        f"row_{key}_reviews",
        three(r["reviewsEffect"]),
        [prefix + f"{rs}{{}} | {r['grounding']} | {gs}{{m:row_{key}_grounding}} | {r['exitCode']} |"],
    )
    add(
        f"row_{key}_grounding",
        three(r["groundingEffect"]),
        [prefix + f"{rs}{{m:row_{key}_reviews}} | {r['grounding']} | {gs}{{}} | {r['exitCode']} |"],
    )

# Stem collision check: no alternative may contain another metric's alternative, and no alternative may be a
# suffix of a sibling alternative. A phrase pinned by {m:key} neighbours is a table cell; twins share a stem by design.


def stem(phrase: str) -> str:
    return re.sub(r"\{m:[a-z0-9_]+\}", "0", phrase).replace("{}", "0")


entries = list(anchors.items())
for key, phrases in entries:
    for phrase in phrases:
        for other_key, other_phrases in entries:
            for other in other_phrases:
                if key == other_key and phrase == other:
                    continue
                if "{m:" in phrase and "{m:" in other:
                    continue
                a, b = stem(phrase), stem(other)
                if key != other_key and b in a:
                    fail(f'anchor collision: "{phrase}" ({key}) contains "{other}" ({other_key})')
                if key == other_key and a != b and a.endswith(b):
                    fail(f'sibling collision: "{other}" is a suffix of "{phrase}" ({key})')

checked_documents = [
    "README.md",
    "fixture/README.md",
    "docs/adr/ADR-001-the-verdict-is-a-sample-size-claim.md",
    "docs/adr/ADR-002-claim-level-grounding-against-the-contract.md",
    "docs/adr/ADR-003-standard-library-statistics-and-a-stand-in-model.md",
    "docs/adr/ADR-004-a-regression-wins-and-the-service-cannot-disagree.md",
    "docs/adr/ADR-005-what-a-committed-fixture-cannot-establish.md",
]
banner = {
    "path": "docs/assets/banner.svg",
    "figures": {
        "careful_effect_30": "ahead by {}",
        "careful_floor_30": "floor {}",
        "careful_min_n": "{} reviews to know",
        "unflagged_bad_claims": "{} bad claims unflagged",
    },
}

(ROOT / "docs" / "metrics.json").write_text(
    json.dumps(
        {
            "metrics": metrics,
            "anchors": anchors,
            "checked_documents": checked_documents,
            "banner": banner,
            "note": "every value here is produced by running the suite and the experiments; tools/collect_metrics.py wrote it",
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
print(
    f"collect_metrics: {len(metrics)} metrics written to docs/metrics.json ({tests_total} tests, {one(coverage_pct)}% line coverage)"
)
