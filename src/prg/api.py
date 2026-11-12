"""The gate as a FastAPI service: the same functions the CLI calls, behind four routes.

`create_app` imports fastapi inside itself, so importing this module on the default path costs
nothing and a missing extra is reported as a usage error, not an ImportError. The routes call
`gate.run_gate`, `cli.power_payload` and the grounding census and nothing else, so the service
cannot disagree with the command line (ADR-004). The context is loaded once at start-up.
"""

from __future__ import annotations

from pathlib import Path

from . import report
from .exit_codes import NAMES, PrgError
from .gate import Context, grounding_census, load_context, run_gate


def create_app(
    project_dir: Path,
    data_dir: Path,
    generations_dir: Path,
    reviews_dir: Path | None,
    policy_path: Path | None,
    grammar_path: Path,
    template_name: str | None = None,
    context: Context | None = None,
):
    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as exc:
        raise PrgError("the api needs the api extra: pip install 'prompt-regression-gate[api]'") from exc

    ctx = context or load_context(project_dir, data_dir, generations_dir, reviews_dir, policy_path, grammar_path, template_name)
    app = FastAPI(
        title="prompt-regression-gate",
        version="0.1.0",
        description="A PR gate for Prompt Builder template changes: the noise floor of the review sample and the claims no merged-in field supports.",
    )

    def guard(fn, *args):
        try:
            return fn(*args)
        except PrgError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/versions")
    def versions() -> dict:
        return {
            "template": ctx.template.developer_name,
            "activeVersion": ctx.template.active_version,
            "versions": {
                v: {
                    "status": tv.status,
                    "families": sorted(tv.families),
                    "fields": tv.fields,
                    "generations": len(ctx.generations.get(v, {})),
                }
                for v, tv in ctx.template.versions.items()
            },
            "reviewers": ctx.reviews.reviewers if ctx.reviews else [],
        }

    @app.post("/gate")
    def gate(body: dict) -> dict:
        baseline, candidate = body.get("baseline"), body.get("candidate")
        if not baseline or not candidate:
            raise HTTPException(status_code=400, detail="body needs baseline and candidate")
        reviewed_set = body.get("reviewedSet")
        if reviewed_set not in (None, "first30", "all"):
            raise HTTPException(status_code=400, detail="reviewedSet must be first30 or all")
        result = guard(run_gate, ctx, baseline, candidate, reviewed_set)
        summary = report.summarize(ctx, result)
        summary["exitName"] = NAMES[result.exit_code]
        return summary

    @app.get("/ground/{version}/{case_id}")
    def ground(version: str, case_id: str) -> dict:
        grounded = guard(ctx.grounding, version)
        if case_id not in grounded:
            raise HTTPException(status_code=404, detail=f"no generation for case {case_id} in version {version}")
        s = grounded[case_id]
        return {
            "version": version,
            "caseId": case_id,
            "bad": s.bad,
            "claims": [
                {"index": c.index, "text": c.text, "verdict": c.verdict, "atoms": [a.__dict__ for a in c.atoms]} for c in s.claims
            ],
        }

    @app.get("/census/{version}")
    def census(version: str) -> dict:
        return {"version": version, **guard(grounding_census, ctx, version)}

    @app.get("/power")
    def power(baseline: str, candidate: str, reviewedSet: str | None = None) -> dict:  # noqa: N803 (the query name matches the gate body)
        from .cli import power_payload

        if reviewedSet not in (None, "first30", "all"):
            raise HTTPException(status_code=400, detail="reviewedSet must be first30 or all")
        return guard(power_payload, ctx, baseline, candidate, reviewedSet, False)

    return app
