"""Generations in the Connect REST response shape, and the resolved prompt they must match."""

from __future__ import annotations

import json

import pytest

from prg.exit_codes import PrgError
from prg.exports import read_exports
from prg.generations import check_prompts, read_generation, read_generations, render_provider, resolve, write_generation
from prg.metadata import find_template
from prg.policy import load_policy

from .conftest import FIXTURE
from .helpers import edit

FAMILIES = ["Input", "RelatedList", "Flow", "Apex", "EinsteinSearch"]


def test_every_committed_generation_carries_the_response_shape_and_matches_its_resolved_prompt():
    policy = load_policy(FIXTURE / "policy" / "gate-policy.json")
    template = find_template(FIXTURE, FAMILIES)
    exports = read_exports(FIXTURE / "data")
    for identifier in template.versions:
        gens = read_generations(FIXTURE / "generations", identifier)
        assert len(gens) == 200
        assert check_prompts(template.version(identifier), gens, exports, policy) == []


def test_a_generation_file_has_the_documented_keys():
    raw = json.loads(next((FIXTURE / "generations" / "v1").glob("*.json")).read_text(encoding="utf-8"))
    assert set(raw) >= {"generations", "prompt", "promptTemplateDevName", "requestId", "parameters", "generationErrors"}
    assert raw["promptTemplateDevName"] == "Case_Summary"
    assert "text" in raw["generations"][0] and "responseId" in raw["generations"][0]


def test_the_resolved_prompt_replaces_every_merge_field_and_renders_the_related_list():
    policy = load_policy(None)
    template = find_template(FIXTURE, FAMILIES)
    exports = read_exports(FIXTURE / "data")
    case = next(iter(exports.cases.values()))
    prompt = resolve(template.version("v1"), case, exports, policy)
    assert "{!$" not in prompt
    assert f"Subject: {case.fields['Subject']}" in prompt
    assert f"- [{case.comments[0].created}] {case.comments[0].body}" in prompt


def test_the_retriever_version_renders_chunks_and_the_provider_text():
    policy = load_policy(None)
    template = find_template(FIXTURE, FAMILIES)
    exports = read_exports(FIXTURE / "data")
    case = next(iter(exports.cases.values()))
    prompt = resolve(template.version("v3"), case, exports, policy)
    assert f"- ({case.chunks[0].chunk_id}) {case.chunks[0].text}" in prompt
    assert render_provider(case, "CaseSummaryGrounding") in prompt
    assert render_provider(case, "CaseSummaryGrounding").startswith(f"Comment count: {len(case.comments)}. Newest comment: ")


def test_the_provider_text_for_a_case_without_comments_has_an_empty_newest_date():
    exports = read_exports(FIXTURE / "data")
    case = next(iter(exports.cases.values()))
    case.comments = []
    assert render_provider(case, "P") == "Comment count: 0. Newest comment: . Provider: P."


def test_a_contract_field_the_export_lacks_is_refused_by_name(mini):
    path = mini / "force-app" / "main" / "default" / "genAiPromptTemplates" / "Mini_Summary.genAiPromptTemplate-meta.xml"
    edit(path, "{!$Input:Case.Subject}", "{!$Input:Case.Rating}")
    policy = load_policy(None)
    template = find_template(mini, FAMILIES)
    exports = read_exports(mini / "data")
    with pytest.raises(PrgError, match="names field 'Rating', which the export lacks"):
        resolve(template.version("v1"), exports.case("500000000000001AAA"), exports, policy)


def test_a_committed_prompt_that_drifted_from_the_template_is_named(mini):
    policy = load_policy(None)
    template = find_template(mini, FAMILIES)
    exports = read_exports(mini / "data")
    edit(mini / "generations" / "v1" / "500000000000002AAA.json", "Summarize the case.", "Summarise the case.")
    gens = read_generations(mini / "generations", "v1")
    assert check_prompts(template.version("v1"), gens, exports, policy) == ["500000000000002AAA"]


def test_read_generation_refuses_a_missing_key_a_missing_file_and_bad_json(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"generations": [{"text": "a"}], "prompt": "p"}), encoding="utf-8")
    with pytest.raises(PrgError, match="'promptTemplateDevName' is missing"):
        read_generation(p, "v1")
    p.write_text(json.dumps({"generations": [], "prompt": "p", "promptTemplateDevName": "t", "requestId": "r"}), encoding="utf-8")
    with pytest.raises(PrgError, match="generations\\[0\\].text is missing"):
        read_generation(p, "v1")
    p.write_text("{", encoding="utf-8")
    with pytest.raises(PrgError, match="not valid JSON"):
        read_generation(p, "v1")
    with pytest.raises(PrgError, match="generation not found"):
        read_generation(tmp_path / "missing.json", "v1")


def test_read_generations_refuses_an_empty_version_folder(tmp_path):
    with pytest.raises(PrgError, match="no generation files for version v9"):
        read_generations(tmp_path, "v9")


def test_write_then_read_round_trips_text_prompt_and_request_id(tmp_path):
    write_generation(tmp_path / "v1" / "c.json", "T", "v1", "c", "the text", "the prompt", "req-1")
    g = read_generation(tmp_path / "v1" / "c.json", "v1")
    assert (g.text, g.prompt, g.request_id, g.case_id, g.version) == ("the text", "the prompt", "req-1", "c", "v1")
