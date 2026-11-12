"""The command line: every command, every exit code, the outputs it writes."""

from __future__ import annotations

import json

import pytest

from prg.cli import main

from .conftest import FIXTURE
from .helpers import ORDER, edit

C1 = "500000000000001AAA"


def _args(mini, command, *rest):
    return [command, "--project", str(mini), *rest]


def test_gate_exits_two_on_the_fixture_default_and_prints_the_table(capsys):
    code = main(["gate", "--project", str(FIXTURE), "--baseline", "v1", "--candidate", "v3"])
    out = capsys.readouterr().out
    assert code == 2
    assert "verdict: exit 2 (cannot decide)" in out and "reviews    undecided" in out and "would need" in out


def test_gate_exits_one_on_the_fluent_rewrite_and_zero_on_the_careful_one_at_full_review(capsys):
    assert main(["gate", "--project", str(FIXTURE), "--baseline", "v1", "--candidate", "v2", "--quiet"]) == 1
    assert (
        main(["gate", "--project", str(FIXTURE), "--baseline", "v1", "--candidate", "v3", "--reviewed-set", "all", "--quiet"])
        == 0
    )
    assert capsys.readouterr().out == ""


def test_gate_writes_json_markdown_and_html_that_agree_on_the_verdict(tmp_path, mini):
    j, m, h = tmp_path / "g.json", tmp_path / "g.md", tmp_path / "g.html"
    code = main(
        _args(
            mini,
            "gate",
            "--baseline",
            "v1",
            "--candidate",
            "v2",
            "--reviewed-set",
            "all",
            "--json",
            str(j),
            "--markdown",
            str(m),
            "--html",
            str(h),
            "--quiet",
        )
    )
    payload = json.loads(j.read_text(encoding="utf-8"))
    assert payload["exitCode"] == code
    assert f"exit {code}" in m.read_text(encoding="utf-8")
    html = h.read_text(encoding="utf-8")
    assert f"exit {code}:" in html and "table-layout:fixed" in html and "<colgroup>" in html


def test_gate_exits_three_on_an_unknown_version_with_the_versions_named(capsys, mini):
    assert main(_args(mini, "gate", "--baseline", "v1", "--candidate", "v9")) == 3
    assert "no version 'v9'" in capsys.readouterr().err


def test_gate_exits_three_on_a_malformed_review_file(capsys, mini):
    edit(mini / "reviews" / "reviewer_a.csv", ",3,", ",9,")
    assert main(_args(mini, "gate", "--baseline", "v1", "--candidate", "v2")) == 3
    assert "reviewer_a.csv" in capsys.readouterr().err


def test_gate_exits_three_on_a_missing_project(capsys, tmp_path):
    assert main(["gate", "--project", str(tmp_path), "--baseline", "v1", "--candidate", "v2"]) == 3
    assert "no .genAiPromptTemplate-meta.xml" in capsys.readouterr().err


def test_a_bad_argument_exits_three_and_help_exits_zero(capsys):
    assert main(["gate", "--nope"]) == 3
    assert main(["--help"]) == 0
    assert main([]) == 3


def test_power_prints_the_arithmetic_and_writes_json(capsys, tmp_path):
    j = tmp_path / "p.json"
    assert main(["power", "--project", str(FIXTURE), "--baseline", "v1", "--candidate", "v3", "--json", str(j)]) == 0
    out = capsys.readouterr().out
    assert "noise floor at n" in out and "n for the effect" in out and "reviewer agreement" in out
    payload = json.loads(j.read_text(encoding="utf-8"))
    assert payload["reviews"]["n"] == 30 and "sweep" not in payload


def test_power_with_the_sweep_reports_the_clearing_n_and_the_draws(capsys, mini):
    assert main(_args(mini, "power", "--baseline", "v1", "--candidate", "v2", "--reviewed-set", "all", "--sweep")) == 0
    out = capsys.readouterr().out
    assert "clears at" in out and "draws of 3" in out


def test_power_without_reviews_exits_three(capsys, tmp_path):
    from .helpers import write_corpus

    project = write_corpus(tmp_path, with_reviews=False)
    assert main(_args(project, "power", "--baseline", "v1", "--candidate", "v2")) == 3
    assert "needs a reviews directory" in capsys.readouterr().err


def test_ground_prints_a_census_and_the_bad_claims(capsys, mini, tmp_path):
    j = tmp_path / "g.json"
    assert main(_args(mini, "ground", "--version", "v2", "--limit", "2", "--json", str(j))) == 0
    out = capsys.readouterr().out
    assert out.startswith("v2: 4 summaries") and out.count("nothing in the resolved prompt") + out.count("field") >= 1
    payload = json.loads(j.read_text(encoding="utf-8"))
    assert payload["census"]["summaries"] == 4 and C1 in payload["summaries"]


def test_ground_for_one_case_prints_every_claim(capsys, mini):
    assert main(_args(mini, "ground", "--version", "v2", "--case", C1)) == 0
    out = capsys.readouterr().out
    assert "contradicted" in out and "misgrounded" in out and "[1]" in out


def test_ground_refuses_an_unknown_case_or_a_version_without_generations(capsys, mini):
    assert main(_args(mini, "ground", "--version", "v2", "--case", "nope")) == 3
    assert main(_args(mini, "ground", "--version", "v9")) == 3


def test_explain_prints_the_contract_the_claims_and_the_reviews(capsys, mini):
    assert main(_args(mini, "explain", C1, "v2")) == 0
    out = capsys.readouterr().out
    assert out.startswith("contract of v2: fields Subject")
    assert "reviews: reviewer_a 4, reviewer_b 4, reviewer_c 5; flagged by any reviewer: yes" in out
    assert main(_args(mini, "explain", C1, "v2", "--ungrouped")) == 0
    assert main(_args(mini, "explain", "nope", "v2")) == 3


def test_explain_groups_atoms_that_share_a_verdict_and_a_source(capsys, mini):
    from .helpers import set_summary

    set_summary(mini, "v1", C1, "Priya Natarajan, Priya Natarajan, Priya Natarajan, Priya Natarajan and Priya Natarajan called.")
    assert main(_args(mini, "explain", C1, "v1")) == 0
    out = capsys.readouterr().out
    assert "and 2 more" in out
    main(_args(mini, "explain", C1, "v1", "--ungrouped"))
    assert "and 2 more" not in capsys.readouterr().out


def test_compare_prints_both_versions_with_their_scores(capsys, mini):
    assert main(_args(mini, "compare", "v1", "v2", C1)) == 0
    out = capsys.readouterr().out
    assert out.count("reviews:") == 2 and "mean 3.33" in out and "mean 4.33" in out
    assert main(_args(mini, "compare", "v1", "v2", "nope")) == 3


def test_generate_with_the_fixture_adapter_reproduces_the_committed_generations_for_a_seed(tmp_path, capsys):
    out_dir = tmp_path / "gens"
    assert (
        main(
            [
                "generate",
                "--project",
                str(FIXTURE),
                "--version",
                "v1",
                "--adapter",
                "fixture",
                "--out",
                str(out_dir),
                "--seed",
                "2026",
                "--limit",
                "3",
            ]
        )
        == 0
    )
    assert "wrote 3 generations for v1" in capsys.readouterr().out
    for path in sorted(out_dir.glob("v1/*.json")):
        mine = json.loads(path.read_text(encoding="utf-8"))
        theirs = json.loads((FIXTURE / "generations" / "v1" / path.name).read_text(encoding="utf-8"))
        assert mine["generations"][0]["text"] == theirs["generations"][0]["text"]
        assert mine["prompt"] == theirs["prompt"]


def test_generate_refuses_a_missing_fault_model_and_an_unknown_version(tmp_path, capsys):
    assert (
        main(
            [
                "generate",
                "--project",
                str(FIXTURE),
                "--version",
                "v1",
                "--out",
                str(tmp_path),
                "--fault-model",
                str(tmp_path / "nope.json"),
            ]
        )
        == 3
    )
    assert "fault model not found" in capsys.readouterr().err
    assert main(["generate", "--project", str(FIXTURE), "--version", "v9", "--out", str(tmp_path)]) == 3


def test_generate_with_a_live_adapter_and_no_key_exits_three_without_touching_the_network(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert (
        main(
            [
                "generate",
                "--project",
                str(FIXTURE),
                "--version",
                "v1",
                "--adapter",
                "openai",
                "--out",
                str(tmp_path),
                "--limit",
                "1",
            ]
        )
        == 3
    )
    assert "OPENAI_API_KEY" in capsys.readouterr().err
    assert (
        main(
            [
                "generate",
                "--project",
                str(FIXTURE),
                "--version",
                "v1",
                "--adapter",
                "gemini",
                "--out",
                str(tmp_path),
                "--limit",
                "1",
            ]
        )
        == 3
    )
    assert "GEMINI_API_KEY" in capsys.readouterr().err


def test_policy_prints_every_input_with_its_reason(capsys):
    assert main(["policy", "--project", str(FIXTURE)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("policy from") and "alpha = 0.05" in out and "reviewed_set = first30" in out and "(" in out


def test_policy_falls_back_to_the_built_in_defaults_without_a_file(capsys, tmp_path):
    assert main(["policy", "--project", str(tmp_path)]) == 0
    assert "built-in defaults" in capsys.readouterr().out


def test_serve_without_uvicorn_exits_three(capsys, monkeypatch, mini):
    import builtins

    real = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name == "uvicorn":
            raise ImportError("no uvicorn")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)
    pytest.importorskip("fastapi")
    assert main(_args(mini, "serve")) == 3
    assert "api extra" in capsys.readouterr().err


def test_serve_hands_the_app_to_uvicorn_with_the_host_and_port(monkeypatch, mini):
    pytest.importorskip("fastapi")
    import uvicorn

    captured = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: captured.update(kw))
    assert main(_args(mini, "serve", "--port", "8123")) == 0
    assert captured["port"] == 8123 and captured["host"] == "127.0.0.1"


def test_the_reviewed_set_flag_overrides_the_policy(capsys, mini):
    main(_args(mini, "gate", "--baseline", "v1", "--candidate", "v2", "--reviewed-set", "all"))
    assert f"reviewed set all, {len(ORDER)} cases" in capsys.readouterr().out
