"""The four renderings of one summary agree with each other and with the gate."""

from __future__ import annotations

import json

from prg import report
from prg.gate import run_gate


def test_the_summary_carries_the_verdict_the_versions_and_the_agreement(mini_ctx):
    s = report.summarize(mini_ctx, run_gate(mini_ctx, "v1", "v2", "all"))
    assert s["exitName"] in ("ship", "blocked", "cannot decide")
    assert set(s["versions"]) == {"v1", "v2"} and s["versions"]["v2"]["families"] == [
        "Apex",
        "EinsteinSearch",
        "Input",
        "RelatedList",
    ]
    assert s["agreement"]["pairs"] and s["reviewedCases"] == 4 and s["policy"]["alpha"] == 0.05


def test_text_markdown_and_html_quote_the_same_effect(mini_ctx):
    s = report.summarize(mini_ctx, run_gate(mini_ctx, "v1", "v2", "all"))
    effect = f"{s['reviews']['effect']:+.3f}"
    assert effect in report.text(s) and effect in report.markdown(s) and effect in report.html_report(s)


def test_the_json_rendering_round_trips(mini_ctx):
    s = report.summarize(mini_ctx, run_gate(mini_ctx, "v1", "v2", "all"))
    assert json.loads(report.to_json(s)) == s


def test_a_refused_dimension_is_rendered_in_every_format(mini_ctx):
    s = report.summarize(mini_ctx, run_gate(mini_ctx, "v1", "v2", "all"))
    s["grounding"] = {**s["grounding"], "direction": "refused", "refusal": "version v2: nope"}
    s["versions"]["v2"]["grounding"] = {"refused": "nope"}
    assert "refused" in report.text(s) and "refused" in report.markdown(s) and "refused" in report.html_report(s)


def test_the_html_lists_the_candidates_bad_claims_up_to_the_limit(mini_ctx):
    s = report.summarize(mini_ctx, run_gate(mini_ctx, "v1", "v2", "all"))
    html = report.html_report(s, mini_ctx.grounded, limit=1)
    assert html.count("class='verdict-") == 1
    assert report.html_report(s, mini_ctx.grounded).count("class='verdict-") == 4


def test_the_html_escapes_text_and_colours_the_badge_by_exit_code(mini_ctx):
    s = report.summarize(mini_ctx, run_gate(mini_ctx, "v1", "v2", "all"))
    s["reasons"] = ["<b>not bold</b>"]
    html = report.html_report(s)
    assert "&lt;b&gt;not bold&lt;/b&gt;" in html and "id='badge'" in html
    s["exitCode"] = 7
    assert "#555" in report.html_report(s)


def test_the_grounding_text_names_the_source_or_the_absence_of_one(mini_ctx):
    text = report.grounding_text(mini_ctx.grounding("v2")["500000000000002AAA"])
    assert "nothing in the resolved prompt" in text and "field Priority" in text


def test_the_power_text_handles_a_never_clearing_sweep_and_no_sweep():
    payload = {
        "baseline": "v1",
        "candidate": "v2",
        "reviewers": ["a"],
        "alpha": 0.05,
        "power": 0.8,
        "reviews": {
            "n": 4,
            "effect": 0.1,
            "sd": 0.2,
            "ciLow": -0.1,
            "ciHigh": 0.3,
            "t": 1.0,
            "p": 0.4,
            "bootstrapLow": -0.1,
            "bootstrapHigh": 0.3,
            "sign": {"wins": 1, "losses": 1, "ties": 2, "p": 1.0},
            "floor": 0.5,
            "minN": None,
            "direction": "undecided",
        },
        "agreement": {"meanAgreementPct": 50.0, "meanKappa": 0.0},
        "clearsAt": None,
    }
    text = report.power_text(payload)
    assert "never along the committed order" in text and "none (the effect is zero)" in text
    del payload["clearsAt"]
    assert "clears at" not in report.power_text(payload)
