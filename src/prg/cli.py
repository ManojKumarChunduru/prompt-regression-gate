"""The command line: gate, power, ground, explain, compare, generate, policy, serve.

Every command loads the same context (template, exports, generations, reviews, policy, grammar)
and refuses the same malformed inputs with the file and element named (exit 3). `gate` is the
PR check and the only command whose exit code carries a verdict; the others exit 0 when they ran
and 3 when they could not.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

from . import report
from .exit_codes import USAGE, PrgError
from .gate import Context, draws, first_clearing_n, load_context, prefix_sweep, review_dimension, reviewer_agreement, run_gate
from .policy import load_policy


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", type=Path, default=Path("fixture"), help="the SFDX project directory (default: fixture)")
    parser.add_argument("--data", type=Path, default=None, help="the data exports (default: <project>/data)")
    parser.add_argument(
        "--generations", type=Path, default=None, help="the generations directory (default: <project>/generations)"
    )
    parser.add_argument("--reviews", type=Path, default=None, help="the reviews directory (default: <project>/reviews)")
    parser.add_argument(
        "--policy", type=Path, default=None, help="the policy file (default: <project>/policy/gate-policy.json if present)"
    )
    parser.add_argument(
        "--grammar", type=Path, default=None, help="the claim grammar (default: <project>/policy/claim-grammar.json)"
    )
    parser.add_argument("--template", default=None, help="the template developer name, when the project holds more than one")


def paths(args: argparse.Namespace) -> dict:
    project: Path = args.project
    policy = args.policy
    if policy is None and (project / "policy" / "gate-policy.json").exists():
        policy = project / "policy" / "gate-policy.json"
    return {
        "project_dir": project,
        "data_dir": args.data or project / "data",
        "generations_dir": args.generations or project / "generations",
        "reviews_dir": args.reviews or project / "reviews",
        "policy_path": policy,
        "grammar_path": args.grammar or project / "policy" / "claim-grammar.json",
        "template_name": args.template,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prg", description="A PR gate for Prompt Builder template changes.")
    sub = parser.add_subparsers(dest="command", required=True)

    gate = sub.add_parser("gate", help="the verdict on one prompt change: exit 0 ship, 1 blocked, 2 cannot decide, 3 usage")
    add_common(gate)
    gate.add_argument("--baseline", required=True)
    gate.add_argument("--candidate", required=True)
    gate.add_argument("--reviewed-set", choices=["first30", "all"], default=None, help="overrides the policy's reviewed set")
    gate.add_argument("--json", type=Path, default=None, help="write the summary as JSON to this path")
    gate.add_argument("--markdown", type=Path, default=None, help="write the summary as markdown to this path")
    gate.add_argument("--html", type=Path, default=None, help="write the report as HTML to this path")
    gate.add_argument("--quiet", action="store_true")

    power = sub.add_parser(
        "power", help="the arithmetic alone: effect, interval, noise floor, minimum n, agreement, the sweep and the draws"
    )
    add_common(power)
    power.add_argument("--baseline", required=True)
    power.add_argument("--candidate", required=True)
    power.add_argument("--reviewed-set", choices=["first30", "all"], default=None)
    power.add_argument("--sweep", action="store_true", help="also walk the committed order and draw the policy's thirties")
    power.add_argument("--json", type=Path, default=None)

    ground = sub.add_parser("ground", help="every claim of one version, with its verdict and its source")
    add_common(ground)
    ground.add_argument("--version", required=True)
    ground.add_argument("--case", default=None, help="one case id; default: a census of the version plus the bad claims")
    ground.add_argument("--limit", type=int, default=20)
    ground.add_argument("--json", type=Path, default=None)

    explain = sub.add_parser("explain", help="one summary, claim by claim, with the evidence behind every verdict")
    add_common(explain)
    explain.add_argument("case_id")
    explain.add_argument("version")
    explain.add_argument("--ungrouped", action="store_true", help="print every atom on its own line")

    compare = sub.add_parser("compare", help="two versions side by side on one case, with the reviewers' scores")
    add_common(compare)
    compare.add_argument("baseline")
    compare.add_argument("candidate")
    compare.add_argument("case_id")

    generate = sub.add_parser(
        "generate", help="write generations for one version through an adapter (fixture by default; openai and gemini need a key)"
    )
    add_common(generate)
    generate.add_argument("--version", required=True)
    generate.add_argument("--adapter", default="fixture", choices=["fixture", "openai", "gemini"])
    generate.add_argument(
        "--out", type=Path, required=True, help="the generations directory to write <version>/<caseId>.json under"
    )
    generate.add_argument("--seed", type=int, default=7)
    generate.add_argument(
        "--fault-model",
        type=Path,
        default=None,
        help="the fixture adapter's fault model (default: <project>/policy/fault-model.json)",
    )
    generate.add_argument("--model", default=None, help="the live adapters' model name")
    generate.add_argument("--limit", type=int, default=None)

    policy = sub.add_parser("policy", help="print the policy as the gate read it, with a reason per line")
    add_common(policy)

    serve = sub.add_parser("serve", help="the gate as a FastAPI service (needs the api extra)")
    add_common(serve)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    return parser


def _context(args: argparse.Namespace) -> Context:
    return load_context(**paths(args))


def cmd_gate(args: argparse.Namespace) -> int:
    ctx = _context(args)
    result = run_gate(ctx, args.baseline, args.candidate, args.reviewed_set)
    summary = report.summarize(ctx, result)
    if args.json:
        args.json.write_text(report.to_json(summary), encoding="utf-8")
    if args.markdown:
        args.markdown.write_text(report.markdown(summary), encoding="utf-8")
    if args.html:
        args.html.write_text(report.html_report(summary, ctx.grounded), encoding="utf-8")
    if not args.quiet:
        sys.stdout.write(report.text(summary))
    return result.exit_code


def power_payload(ctx: Context, baseline: str, candidate: str, reviewed_set: str | None, sweep: bool) -> dict:
    if ctx.reviews is None:
        raise PrgError("power needs a reviews directory")
    which = reviewed_set or ctx.policy.reviewed_set
    case_ids = ctx.reviews.reviewed_set(which)
    dim = review_dimension(ctx, baseline, candidate, case_ids)
    payload = {
        "baseline": baseline,
        "candidate": candidate,
        "reviewedSet": which,
        "reviewers": ctx.reviews.reviewers,
        "alpha": ctx.policy.alpha,
        "power": ctx.policy.power,
        "reviews": dim.as_dict(),
        "agreement": reviewer_agreement(ctx, baseline, candidate, case_ids),
    }
    if sweep:
        rows = prefix_sweep(ctx, baseline, candidate)
        payload["sweep"] = rows
        payload["clearsAt"] = first_clearing_n(rows)
        payload["draws"] = draws(ctx, baseline, candidate)
    return payload


def cmd_power(args: argparse.Namespace) -> int:
    ctx = _context(args)
    payload = power_payload(ctx, args.baseline, args.candidate, args.reviewed_set, args.sweep)
    if args.json:
        args.json.write_text(report.to_json(payload), encoding="utf-8")
    sys.stdout.write(report.power_text(payload))
    return 0


def cmd_ground(args: argparse.Namespace) -> int:
    ctx = _context(args)
    grounded = ctx.grounding(args.version)
    if args.case:
        if args.case not in grounded:
            raise PrgError(f"no generation for case {args.case} in version {args.version}")
        sys.stdout.write(report.grounding_text(grounded[args.case]))
        return 0
    from .grounding import census

    c = census(grounded)
    sys.stdout.write(
        f"{args.version}: {c['summaries']} summaries, {c['claims']} claims: {c['supported']} supported, "
        f"{c['unsupported']} unsupported, "
        f"{c['contradicted']} contradicted, {c['misgrounded']} mis-grounded, {c['unverifiable']} unverifiable ({c['bad']} bad)\n"
    )
    shown = 0
    for case_id, s in grounded.items():
        for claim in s.claims:
            if claim.verdict in ("unsupported", "contradicted", "misgrounded") and shown < args.limit:
                worst = [a for a in claim.atoms if a.verdict == claim.verdict][0]
                where = (
                    f"{worst.source_kind} {worst.source_ref}".strip()
                    if worst.source_kind != "none"
                    else "nothing in the resolved prompt"
                )
                sys.stdout.write(
                    f"  {case_id} [{claim.index}] {claim.verdict:12} {claim.text}\n      {worst.kind} {worst.value}: {where}\n"
                )
                shown += 1
    if args.json:
        payload = {
            "version": args.version,
            "census": c,
            "summaries": {
                cid: [
                    {"index": cl.index, "text": cl.text, "verdict": cl.verdict, "atoms": [a.__dict__ for a in cl.atoms]}
                    for cl in s.claims
                ]
                for cid, s in grounded.items()
            },
        }
        args.json.write_text(report.to_json(payload), encoding="utf-8")
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    ctx = _context(args)
    grounded = ctx.grounding(args.version)
    if args.case_id not in grounded:
        raise PrgError(f"no generation for case {args.case_id} in version {args.version}")
    version = ctx.template.version(args.version)
    sys.stdout.write(
        f"contract of {args.version}: fields {', '.join(version.fields)}; families {', '.join(sorted(version.families))}\n"
    )
    sys.stdout.write(report.grounding_text(grounded[args.case_id], grouped=not args.ungrouped))
    if ctx.reviews and args.case_id in ctx.reviews.order:
        scores = ", ".join(f"{r} {ctx.reviews.score(r, args.case_id, args.version)}" for r in ctx.reviews.reviewers)
        sys.stdout.write(
            f"reviews: {scores}; flagged by any reviewer: "
            f"{'yes' if ctx.reviews.flagged_by_any(args.case_id, args.version) else 'no'}\n"
        )
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    ctx = _context(args)
    for v in (args.baseline, args.candidate):
        grounded = ctx.grounding(v)
        if args.case_id not in grounded:
            raise PrgError(f"no generation for case {args.case_id} in version {v}")
        sys.stdout.write(report.grounding_text(grounded[args.case_id]))
        if ctx.reviews and args.case_id in ctx.reviews.order:
            scores = ", ".join(f"{r} {ctx.reviews.score(r, args.case_id, v)}" for r in ctx.reviews.reviewers)
            sys.stdout.write(f"  reviews: {scores} (mean {ctx.reviews.case_mean(args.case_id, v):.2f})\n")
        sys.stdout.write("\n")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    import json

    from .adapters import load_adapter
    from .generations import resolve, write_generation

    p = paths(args)
    ctx = load_context(**p, versions=[])
    version = ctx.template.version(args.version)
    adapter = load_adapter(args.adapter)
    case_ids = list(ctx.exports.cases)[: args.limit] if args.limit else list(ctx.exports.cases)
    if args.adapter == "fixture":
        fault_path = args.fault_model or p["project_dir"] / "policy" / "fault-model.json"
        try:
            fault_model = json.loads(fault_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise PrgError(f"fault model not found: {fault_path}") from exc
        if args.version not in fault_model["versions"]:
            raise PrgError(f"{fault_path}: no rates for version {args.version}")
        model = dict(fault_model["versions"][args.version])
        model["invented_templates"] = fault_model["invented_sentences"]["templates"]
        contacts = sorted({c.value("Contact.Name") or "" for c in ctx.exports.cases.values()} - {""})
    written = 0
    for case_id in case_ids:
        case = ctx.exports.case(case_id)
        prompt = resolve(version, case, ctx.exports, ctx.policy)
        if args.adapter == "fixture":
            text, _ = adapter.generate(case, version, random.Random(f"{args.seed}:{args.version}:{case_id}"), model, contacts)
        else:
            text = adapter.generate(prompt, args.model)
        write_generation(
            args.out / args.version / f"{case_id}.json",
            ctx.template.developer_name,
            args.version,
            case_id,
            text,
            prompt,
            f"req-{args.adapter}-{written:04d}",
        )
        written += 1
    sys.stdout.write(
        f"wrote {written} generations for {args.version} with the {args.adapter} adapter under {args.out / args.version}\n"
    )
    return 0


def cmd_policy(args: argparse.Namespace) -> int:
    p = paths(args)
    policy = load_policy(p["policy_path"])
    sys.stdout.write(f"policy from {policy.source}\n")
    for line in policy.lines():
        sys.stdout.write(f"  {line}\n")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .api import create_app

    try:
        import uvicorn
    except ImportError as exc:
        raise PrgError("prg serve needs the api extra: pip install 'prompt-regression-gate[api]'") from exc
    app = create_app(**paths(args))
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


COMMANDS = {
    "gate": cmd_gate,
    "power": cmd_power,
    "ground": cmd_ground,
    "explain": cmd_explain,
    "compare": cmd_compare,
    "generate": cmd_generate,
    "policy": cmd_policy,
    "serve": cmd_serve,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return USAGE if exc.code not in (0, None) else 0
    try:
        return COMMANDS[args.command](args)
    except PrgError as exc:
        sys.stderr.write(f"prg: {exc}\n")
        return USAGE


if __name__ == "__main__":
    sys.exit(main())
