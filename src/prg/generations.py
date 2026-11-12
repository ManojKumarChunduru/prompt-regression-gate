"""Reads and writes generations in the Connect REST response shape, and resolves a template.

One file per case per version, in the shape `POST /einstein/prompt-templates/{name}/generations`
returns: `generations[0].text` is the summary and `prompt` is the resolved prompt. The probe
class writes this shape from an org, the fixture adapter writes it offline, and the gate reads
one shape. `resolve` builds the resolved prompt from a version's content and a case through the
grounding contract; a generation whose `prompt` differs from it is refused, because then the
contract and what the model read have drifted apart.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .exit_codes import PrgError
from .exports import Case, Exports
from .metadata import TemplateVersion
from .policy import Policy


@dataclass
class Generation:
    version: str
    case_id: str
    text: str
    prompt: str
    request_id: str
    path: str


def render_related_list(case: Case, policy: Policy) -> str:
    return "\n".join(policy.related_list_rendering.format(CreatedDate=c.created, CommentBody=c.body) for c in case.comments)


def render_retriever(case: Case, policy: Policy) -> str:
    return "\n".join(policy.retriever_rendering.format(ChunkId=c.chunk_id, Text=c.text) for c in case.chunks)


def render_provider(case: Case, provider: str) -> str:
    """A data provider's Prompt output. The fixture's Apex provider returns the comment count and the
    newest comment date, which is what `CaseSummaryGrounding.cls` computes; declared in ADR-005."""
    newest = max((c.created for c in case.comments), default="")
    return f"Comment count: {len(case.comments)}. Newest comment: {newest}. Provider: {provider}."


def resolve(version: TemplateVersion, case: Case, exports: Exports, policy: Policy) -> str:
    """The resolved prompt: the content with every merge field replaced by its value."""
    text = version.content
    for m in version.merge_fields:
        if m.family == "Input":
            name = m.field_name or ""
            if name not in exports.columns:
                raise PrgError(f"version {version.identifier}: {m.raw} names field {name!r}, which the export lacks")
            value = case.value(name) or ""
        elif m.family == "RelatedList":
            value = render_related_list(case, policy)
        elif m.family == "EinsteinSearch":
            value = render_retriever(case, policy)
        else:
            value = render_provider(case, m.provider or "")
        text = text.replace(m.raw, value)
    return text


def read_generation(path: Path, version: str) -> Generation:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PrgError(f"generation not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PrgError(f"{path}: not valid JSON ({exc.msg} at line {exc.lineno})") from exc
    for key in ("generations", "prompt", "promptTemplateDevName", "requestId"):
        if key not in raw:
            raise PrgError(f"{path}: {key!r} is missing from the generations response")
    if not raw["generations"] or "text" not in raw["generations"][0]:
        raise PrgError(f"{path}: generations[0].text is missing")
    return Generation(
        version=version,
        case_id=path.stem,
        text=raw["generations"][0]["text"],
        prompt=raw["prompt"],
        request_id=raw["requestId"],
        path=str(path),
    )


def read_generations(generations_dir: Path, version: str) -> dict[str, Generation]:
    folder = Path(generations_dir) / version
    files = sorted(folder.glob("*.json"))
    if not files:
        raise PrgError(f"{folder}: no generation files for version {version}")
    return {f.stem: read_generation(f, version) for f in files}


def write_generation(path: Path, template_name: str, version: str, case_id: str, text: str, prompt: str, request_id: str) -> None:
    payload = {
        "generations": [{"text": text, "responseId": f"{request_id}-0", "parameters": {"versionIdentifier": version}}],
        "prompt": prompt,
        "promptTemplateDevName": template_name,
        "requestId": request_id,
        "parameters": {"Input:Case": {"id": case_id}},
        "generationErrors": [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def check_prompts(version: TemplateVersion, generations: dict[str, Generation], exports: Exports, policy: Policy) -> list[str]:
    """Case ids whose committed prompt differs from the resolved one: the contract drifted."""
    drifted = []
    for case_id, generation in generations.items():
        if resolve(version, exports.case(case_id), exports, policy) != generation.prompt:
            drifted.append(case_id)
    return drifted
