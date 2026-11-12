"""The committed fixture against its planted truth, and the generator against itself."""

from __future__ import annotations

import filecmp
import json
import os
import subprocess
import sys

import pytest

from prg.gate import run_gate

from .conftest import FIXTURE, ROOT

BAD = ("unsupported", "contradicted", "misgrounded")


def test_the_truth_describes_the_committed_fixture(truth, ctx):
    assert truth["cases"] == len(ctx.exports.cases) == 200
    assert truth["comments"] == ctx.exports.comments_total
    assert truth["chunks"] == ctx.exports.chunks_total
    assert truth["versions"] == ctx.versions() == ["v1", "v2", "v3"]
    assert truth["reviewers"] == ctx.reviews.reviewers
    assert truth["canonicalThirty"] == ctx.reviews.reviewed_set("first30")


@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_every_planted_bad_claim_is_recovered_with_its_kind_and_no_clean_claim_is_flagged(truth, ctx, version):
    grounded = ctx.grounding(version)
    planted_total = recovered = 0
    false_positives = []
    for case_id, planted in truth["faults"][version].items():
        verdicts = {c.text: c.verdict for c in grounded[case_id].claims}
        planted_bad = {p["sentence"]: p["kind"] for p in planted if p["kind"] in BAD}
        for sentence, kind in planted_bad.items():
            planted_total += 1
            if verdicts.get(sentence) == kind:
                recovered += 1
        for sentence, verdict in verdicts.items():
            if verdict in BAD and sentence not in planted_bad:
                false_positives.append((case_id, sentence))
    expected = sum(v for k, v in truth["faultsByVersion"][version].items() if k in BAD)
    assert planted_total == expected
    assert recovered == planted_total
    assert false_positives == []


@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_every_planted_unverifiable_sentence_and_no_other_is_unverifiable(truth, ctx, version):
    grounded = ctx.grounding(version)
    for case_id, planted in truth["faults"][version].items():
        found = {c.text for c in grounded[case_id].claims if c.verdict == "unverifiable"}
        expected = {p["sentence"] for p in planted if p["kind"] == "unverifiable"}
        assert found == expected, case_id


def test_the_planted_bad_claim_total_is_the_floor_the_readme_quotes(truth):
    total = sum(v for kinds in truth["faultsByVersion"].values() for k, v in kinds.items() if k in BAD)
    assert total == 227


@pytest.mark.parametrize("index", range(12))
def test_every_planted_gate_verdict_is_reproduced_by_the_gate(truth, ctx, index):
    expected = truth["verdicts"][index]
    result = run_gate(ctx, expected["baseline"], expected["candidate"], expected["reviewedSet"])
    assert result.exit_code == expected["exitCode"], expected
    assert result.reviews.direction == expected["reviews"]["direction"]
    assert result.grounding.direction == expected["grounding"]["direction"]
    assert result.reviews.test.mean_diff == pytest.approx(expected["reviews"]["effect"], abs=1e-3)
    assert result.grounding.test.mean_diff == pytest.approx(expected["grounding"]["effect"], abs=1e-3)


def test_the_truth_used_published_critical_values_not_the_gates_distribution(truth):
    for v in truth["verdicts"]:
        assert v["reviews"]["critical"] in (2.045, 1.972)
        assert v["grounding"]["critical"] == 1.972


def test_the_gate_matrix_tells_the_three_stories(ctx):
    fluent_30 = run_gate(ctx, "v1", "v2", "first30")
    fluent_all = run_gate(ctx, "v1", "v2", "all")
    careful_30 = run_gate(ctx, "v1", "v3", "first30")
    careful_all = run_gate(ctx, "v1", "v3", "all")
    # The fluent rewrite: reviewers prefer it and the gate blocks it on grounding, at thirty and at two hundred.
    assert fluent_30.reviews.direction == "better" and fluent_30.grounding.direction == "worse" and fluent_30.exit_code == 1
    assert fluent_all.exit_code == 1
    # The careful rewrite: thirty reviews cannot tell, two hundred can, and the grounding is not worse.
    assert careful_30.reviews.direction == "undecided" and careful_30.exit_code == 2
    assert careful_all.reviews.direction == "better" and careful_all.grounding.direction != "worse" and careful_all.exit_code == 0
    # Rolling the fluent rewrite back: better grounding, worse reviews, blocked.
    assert run_gate(ctx, "v2", "v1", "all").exit_code == 1


def test_the_careful_rewrite_at_thirty_sits_below_the_floor_and_names_a_minimum_n(ctx):
    r = run_gate(ctx, "v1", "v3", "first30")
    assert 0 < r.reviews.test.mean_diff < r.reviews.floor
    assert r.reviews.min_n is not None and r.reviews.min_n > 30


def test_two_runs_of_the_gate_are_byte_identical(ctx):
    from prg import report

    a = report.to_json(report.summarize(ctx, run_gate(ctx, "v1", "v3", "first30")))
    b = report.to_json(report.summarize(ctx, run_gate(ctx, "v1", "v3", "first30")))
    assert a == b


def _regenerate(target, hash_seed: str):
    env = dict(os.environ, PYTHONHASHSEED=hash_seed)
    subprocess.run(
        [sys.executable, "-I", str(FIXTURE / "generate.py"), "--out", str(target)],
        cwd=ROOT,
        check=True,
        env=env,
        capture_output=True,
    )


def _differences(a, b) -> list[str]:
    out = []
    cmp = filecmp.dircmp(
        a, b, ignore=["README.md", "generate.py", "policy", "force-app", "sfdx-project.json", "broken", "__pycache__"]
    )

    def walk(d):
        out.extend(d.diff_files + d.left_only + d.right_only)
        for sub in d.subdirs.values():
            walk(sub)

    walk(cmp)
    return out


@pytest.mark.slow
def test_the_generator_is_byte_identical_under_two_hash_seeds_and_to_the_committed_fixture(tmp_path):
    _regenerate(tmp_path / "a", "1")
    _regenerate(tmp_path / "b", "4242")
    assert _differences(tmp_path / "a", tmp_path / "b") == []
    assert _differences(tmp_path / "a", FIXTURE) == []


def test_the_committed_truth_is_valid_json_with_the_documented_sections():
    raw = json.loads((FIXTURE / "EXPECTED_VERDICTS.json").read_text(encoding="utf-8"))
    assert set(raw) >= {
        "seed",
        "cases",
        "comments",
        "chunks",
        "versions",
        "reviewers",
        "canonicalThirty",
        "faultsByVersion",
        "faults",
        "verdicts",
    }
    assert len(raw["verdicts"]) == 12 and len(raw["canonicalThirty"]) == 30
