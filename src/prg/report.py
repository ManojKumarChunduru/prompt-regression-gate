"""Renders the gate's output as text, JSON, markdown and HTML from one summary dictionary.

The four formats exist for four readers: text for the terminal, JSON for a pipeline, markdown for
the GitHub job summary, HTML for the screenshots. They are all rendered from the same dictionary,
so a figure cannot differ between them.
"""

from __future__ import annotations

import html
import json

from .exit_codes import NAMES
from .gate import Context, GateResult, grounding_census, reviewer_agreement
from .grounding import GroundedSummary


def summarize(ctx: Context, result: GateResult) -> dict:
    """The one dictionary every format renders."""
    reviewed = ctx.reviews.reviewed_set(result.reviewed_set) if ctx.reviews else []
    out = result.as_dict()
    out["exitName"] = NAMES[result.exit_code]
    out["template"] = {
        "developerName": ctx.template.developer_name,
        "type": ctx.template.type,
        "activeVersion": ctx.template.active_version,
    }
    out["versions"] = {
        v: {
            "status": ctx.template.versions[v].status,
            "families": sorted(ctx.template.versions[v].families),
            "fields": ctx.template.versions[v].fields,
            "generations": len(ctx.generations.get(v, {})),
            "grounding": grounding_census(ctx, v) if v in ctx.grounded else {"refused": ctx.refused.get(v, "no generations")},
        }
        for v in (result.baseline, result.candidate)
    }
    out["reviewers"] = ctx.reviews.reviewers if ctx.reviews else []
    out["reviewedCases"] = len(reviewed)
    out["agreement"] = reviewer_agreement(ctx, result.baseline, result.candidate, reviewed) if ctx.reviews and reviewed else None
    out["policy"] = {"alpha": ctx.policy.alpha, "power": ctx.policy.power, "source": ctx.policy.source}
    return out


def _fmt(value, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _dimension_rows(summary: dict) -> list[list[str]]:
    rows = []
    for name in ("reviews", "grounding"):
        d = summary[name]
        unit = "score" if name == "reviews" else "bad claims per case"
        if d["direction"] == "refused":
            rows.append([name, "refused", d["refusal"], "", "", "", "", ""])
            continue
        rows.append(
            [
                name,
                d["direction"],
                f"{_fmt(d['baselineMean'])} to {_fmt(d['candidateMean'])} ({unit})",
                f"{d['effect']:+.3f}",
                f"{_fmt(d['ciLow'])} to {_fmt(d['ciHigh'])}",
                _fmt(d["p"], 4),
                _fmt(d["floor"]),
                str(d["minN"]) if d["minN"] else "none",
            ]
        )
    return rows


HEADERS = ["dimension", "verdict", "baseline to candidate", "effect", "95% interval", "p", "floor at n", "n for the effect"]


def text(summary: dict) -> str:
    lines = [
        f"prompt-regression-gate: {summary['template']['developerName']} {summary['baseline']} -> {summary['candidate']} "
        f"(reviewed set {summary['reviewedSet']}, {summary['reviewedCases']} cases, {len(summary['reviewers'])} reviewers)",
        "",
    ]
    rows = _dimension_rows(summary)
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(HEADERS)]
    lines.append("  ".join(h.ljust(w) for h, w in zip(HEADERS, widths, strict=True)))
    for r in rows:
        lines.append("  ".join(c.ljust(w) for c, w in zip(r, widths, strict=True)))
    lines.append("")
    for v, info in summary["versions"].items():
        g = info["grounding"]
        if "refused" in g:
            lines.append(f"{v}: grounding refused ({g['refused']})")
        else:
            lines.append(
                f"{v}: {g['summaries']} summaries, {g['claims']} claims: {g['supported']} supported, {g['unsupported']} unsupported, "
                f"{g['contradicted']} contradicted, {g['misgrounded']} mis-grounded, {g['unverifiable']} unverifiable"
            )
    if summary["agreement"]:
        a = summary["agreement"]
        lines.append(f"reviewers agree on {a['meanAgreementPct']}% of preferences (mean kappa {a['meanKappa']})")
    lines.append("")
    lines.append(f"verdict: exit {summary['exitCode']} ({summary['exitName']})")
    for reason in summary["reasons"]:
        lines.append(f"  {reason}")
    return "\n".join(lines) + "\n"


def markdown(summary: dict) -> str:
    lines = [
        f"## prompt-regression-gate: `{summary['baseline']}` to `{summary['candidate']}` on `{summary['template']['developerName']}`",
        "",
        f"Reviewed set `{summary['reviewedSet']}`: {summary['reviewedCases']} cases, {len(summary['reviewers'])} reviewers. "
        f"Verdict: **exit {summary['exitCode']} ({summary['exitName']})**.",
        "",
        "| " + " | ".join(HEADERS) + " |",
        "| " + " | ".join("---" for _ in HEADERS) + " |",
    ]
    for r in _dimension_rows(summary):
        lines.append("| " + " | ".join(r) + " |")
    lines.append("")
    for reason in summary["reasons"]:
        lines.append(f"- {reason}")
    lines.append("")
    lines.append("| version | summaries | claims | supported | unsupported | contradicted | mis-grounded | unverifiable |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for v, info in summary["versions"].items():
        g = info["grounding"]
        if "refused" in g:
            lines.append(f"| `{v}` | refused | {g['refused']} | | | | | |")
        else:
            lines.append(
                f"| `{v}` | {g['summaries']} | {g['claims']} | {g['supported']} | {g['unsupported']} | {g['contradicted']} | {g['misgrounded']} | {g['unverifiable']} |"
            )
    return "\n".join(lines) + "\n"


def html_report(summary: dict, grounded: dict[str, dict[str, GroundedSummary]] | None = None, limit: int = 40) -> str:
    code = summary["exitCode"]
    badge_colour = {0: "#2e7d32", 1: "#c62828", 2: "#ef6c00"}.get(code, "#555")
    parts = [
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><title>prompt-regression-gate report</title>",
        "<style>body{font-family:system-ui,sans-serif;margin:24px;color:#1a1a1a;max-width:1320px}",
        "table{border-collapse:collapse;table-layout:fixed;width:100%;margin:12px 0}th,td{border:1px solid #ccc;padding:6px 8px;text-align:left;",
        "overflow-wrap:anywhere;vertical-align:top;font-size:14px}th{background:#f3f3f3}",
        ".badge{display:inline-block;padding:4px 10px;border-radius:4px;color:#fff;font-weight:600}",
        ".verdict-supported{color:#2e7d32}.verdict-unsupported{color:#c62828}.verdict-contradicted{color:#b71c1c;font-weight:600}",
        ".verdict-misgrounded{color:#ef6c00}.verdict-unverifiable{color:#777}code{background:#f3f3f3;padding:1px 4px}</style></head><body>",
        f"<h1 id='header'>prompt-regression-gate: <code>{html.escape(summary['baseline'])}</code> to <code>{html.escape(summary['candidate'])}</code></h1>",
        f"<p>Template <code>{html.escape(summary['template']['developerName'])}</code> ({html.escape(summary['template']['type'])}), reviewed set "
        f"<code>{html.escape(summary['reviewedSet'])}</code>: {summary['reviewedCases']} cases, {len(summary['reviewers'])} reviewers. "
        f"<span class='badge' id='badge' style='background:{badge_colour}'>exit {code}: {html.escape(summary['exitName'])}</span></p>",
        "<h2 id='dimensions'>The two dimensions</h2><table><colgroup><col style='width:9%'><col style='width:8%'><col style='width:22%'>"
        "<col style='width:8%'><col style='width:15%'><col style='width:9%'><col style='width:9%'><col style='width:20%'></colgroup>",
        "<tr>" + "".join(f"<th>{html.escape(h)}</th>" for h in HEADERS) + "</tr>",
    ]
    for r in _dimension_rows(summary):
        parts.append("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in r) + "</tr>")
    parts.append("</table><ul>")
    for reason in summary["reasons"]:
        parts.append(f"<li>{html.escape(reason)}</li>")
    parts.append("</ul>")
    parts.append(
        "<h2 id='census'>Claims by verdict</h2><table><colgroup><col style='width:10%'>"
        + "<col style='width:12.8%'>" * 7
        + "</colgroup>"
    )
    parts.append(
        "<tr><th>version</th><th>summaries</th><th>claims</th><th>supported</th><th>unsupported</th><th>contradicted</th><th>mis-grounded</th><th>unverifiable</th></tr>"
    )
    for v, info in summary["versions"].items():
        g = info["grounding"]
        if "refused" in g:
            parts.append(
                f"<tr><td><code>{html.escape(v)}</code></td><td colspan='7'>refused: {html.escape(g['refused'])}</td></tr>"
            )
        else:
            parts.append(
                f"<tr><td><code>{html.escape(v)}</code></td><td>{g['summaries']}</td><td>{g['claims']}</td><td>{g['supported']}</td>"
                f"<td>{g['unsupported']}</td><td>{g['contradicted']}</td><td>{g['misgrounded']}</td><td>{g['unverifiable']}</td></tr>"
            )
    parts.append("</table>")
    if grounded:
        parts.append(f"<h2 id='claims'>Bad claims in the candidate, first {limit}</h2>")
        parts.append(
            "<table><colgroup><col style='width:14%'><col style='width:11%'><col style='width:45%'><col style='width:30%'></colgroup>"
        )
        parts.append("<tr><th>case</th><th>verdict</th><th>claim</th><th>evidence</th></tr>")
        shown = 0
        for case_id, s in grounded.get(summary["candidate"], {}).items():
            for claim in s.claims:
                if claim.verdict in ("unsupported", "contradicted", "misgrounded") and shown < limit:
                    worst = [a for a in claim.atoms if a.verdict == claim.verdict][0]
                    evidence = f"{worst.kind} {worst.value}: {worst.source_kind} {worst.source_ref}".strip()
                    parts.append(
                        f"<tr><td><code>{html.escape(case_id)}</code></td><td class='verdict-{claim.verdict}'>{claim.verdict}</td>"
                        f"<td>{html.escape(claim.text)}</td><td>{html.escape(evidence)}</td></tr>"
                    )
                    shown += 1
        parts.append("</table>")
    parts.append("</body></html>")
    return "\n".join(parts)


def grounding_text(summary: GroundedSummary, grouped: bool = True) -> str:
    """One summary, claim by claim. Atoms that share a verdict and a source are grouped into one line with a count."""
    lines = [f"{summary.version} {summary.case_id}: {len(summary.claims)} claims, {summary.bad} bad"]
    for claim in summary.claims:
        lines.append(f"  [{claim.index}] {claim.verdict:12} {claim.text}")
        groups: dict[tuple[str, str, str], list[str]] = {}
        for a in claim.atoms:
            groups.setdefault((a.verdict, a.source_kind, a.source_ref), []).append(f"{a.kind} {a.value}")
        for (verdict, source_kind, source_ref), atoms in groups.items():
            where = f"{source_kind} {source_ref}".strip() if source_kind != "none" else "nothing in the resolved prompt"
            if grouped and len(atoms) > 3:
                shown = ", ".join(atoms[:3]) + f" and {len(atoms) - 3} more"
            else:
                shown = ", ".join(atoms)
            lines.append(f"        {verdict:12} {shown}: {where}")
    return "\n".join(lines) + "\n"


def power_text(payload: dict) -> str:
    r = payload["reviews"]
    lines = [
        f"prg power: {payload['baseline']} -> {payload['candidate']} on {r['n']} reviewed cases ({len(payload['reviewers'])} reviewers)",
        f"  observed effect      {r['effect']:+.3f} (candidate minus baseline, mean of the reviewers per case)",
        f"  paired spread        {r['sd']:.3f}",
        f"  95% interval         {r['ciLow']:.3f} to {r['ciHigh']:.3f} (t {r['t']:.2f}, p {r['p']:.4f})",
        f"  bootstrap interval   {r['bootstrapLow']:.3f} to {r['bootstrapHigh']:.3f}",
        f"  sign test            {r['sign']['wins']} wins, {r['sign']['losses']} losses, {r['sign']['ties']} ties (p {r['sign']['p']:.4f})",
        f"  noise floor at n     {r['floor']:.3f} (the smallest effect {r['n']} reviews clear at alpha {payload['alpha']} with power {payload['power']})",
        f"  n for the effect     {r['minN'] if r['minN'] else 'none (the effect is zero)'}",
        f"  verdict              {r['direction']}",
    ]
    a = payload["agreement"]
    lines.append(f"  reviewer agreement   {a['meanAgreementPct']}% of preferences, mean kappa {a['meanKappa']}")
    if payload.get("clearsAt") is not None:
        lines.append(
            f"  clears at            {payload['clearsAt']} reviews along the committed order"
            if payload["clearsAt"]
            else "  clears at            never along the committed order"
        )
    if payload.get("draws"):
        d = payload["draws"]
        lines.append(
            f"  {d['count']} draws of {d['size']}  {d['clearAlpha']} clear alpha ({d['clearAlphaPct']}%), {d['wrongWay']} point the wrong way ({d['wrongWayPct']}%)"
        )
    return "\n".join(lines) + "\n"


def to_json(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
