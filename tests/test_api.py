"""The FastAPI surface: the same functions as the CLI, behind routes. Skipped where the api extra is absent."""

from __future__ import annotations

import pytest

from prg.api import create_app
from prg.exit_codes import PrgError
from prg.gate import run_gate

from .helpers import paths

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

C1 = "500000000000001AAA"


@pytest.fixture
def client(mini, mini_ctx):
    return TestClient(create_app(**paths(mini), context=mini_ctx))


def test_versions_lists_the_template_its_versions_and_the_reviewers(client):
    body = client.get("/versions").json()
    assert body["template"] == "Mini_Summary" and body["activeVersion"] == "v1"
    assert set(body["versions"]) == {"v1", "v2"} and body["versions"]["v2"]["generations"] == 4
    assert body["reviewers"] == ["reviewer_a", "reviewer_b", "reviewer_c"]


def test_gate_over_http_agrees_with_the_gate_in_process(client, mini_ctx):
    body = client.post("/gate", json={"baseline": "v1", "candidate": "v2", "reviewedSet": "all"}).json()
    direct = run_gate(mini_ctx, "v1", "v2", "all")
    assert body["exitCode"] == direct.exit_code
    assert body["reviews"]["p"] == round(direct.reviews.test.p, 6)
    assert body["grounding"]["effect"] == round(direct.grounding.test.mean_diff, 4)


def test_gate_over_http_refuses_a_missing_version_a_bad_set_and_a_missing_body_field(client):
    assert client.post("/gate", json={"baseline": "v1"}).status_code == 400
    assert client.post("/gate", json={"baseline": "v1", "candidate": "v9"}).status_code == 400
    assert client.post("/gate", json={"baseline": "v1", "candidate": "v2", "reviewedSet": "some"}).status_code == 400


def test_ground_returns_every_claim_with_its_atoms(client):
    body = client.get(f"/ground/v2/{C1}").json()
    assert body["bad"] == 3 and [c["verdict"] for c in body["claims"]][:2] == ["supported", "contradicted"]
    assert client.get("/ground/v2/nope").status_code == 404
    assert client.get("/ground/v9/nope").status_code == 400


def test_census_returns_the_counts(client):
    body = client.get("/census/v2").json()
    assert body["version"] == "v2" and body["summaries"] == 4 and body["bad"] == 4


def test_power_over_http_returns_the_arithmetic(client):
    body = client.get("/power", params={"baseline": "v1", "candidate": "v2", "reviewedSet": "all"}).json()
    assert body["reviews"]["n"] == 4 and "floor" in body["reviews"] and "agreement" in body
    assert client.get("/power", params={"baseline": "v1", "candidate": "v2", "reviewedSet": "some"}).status_code == 400


def test_the_openapi_document_names_the_four_routes(client):
    doc = client.get("/openapi.json").json()
    assert {"/versions", "/gate", "/ground/{version}/{case_id}", "/census/{version}", "/power"} <= set(doc["paths"])


def test_create_app_without_fastapi_raises_a_usage_error(monkeypatch, mini):
    import builtins

    real = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name == "fastapi":
            raise ImportError("no fastapi")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse)
    with pytest.raises(PrgError, match="api extra"):
        create_app(**paths(mini))


def test_create_app_loads_its_own_context_when_none_is_given(mini):
    app = create_app(**paths(mini))
    assert TestClient(app).get("/versions").json()["template"] == "Mini_Summary"
