"""Reads the GenAiPromptTemplate metadata and turns each version's content into a grounding contract.

The contract is the set of sources whose values the resolved prompt may contain: the fields named
by `{!$Input:Case.<Field>}`, the related list named by `{!$RelatedList:...}`, the data providers
named by `{!$Flow:...}` and `{!$Apex:...}`, and the retriever named by `{!$EinsteinSearch:...}`.
A claim in a summary is grounded only if a source in the contract supports it: the model could
not have read anything else. The reader validates at the boundary and refuses an unknown
merge-field family, a version without an identifier, or a template without the active version,
each with the file and the element named.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .exit_codes import PrgError

NS = "{http://soap.sforce.com/2006/04/metadata}"
MERGE = re.compile(r"\{!\$(\w+):([\w.]+)\}")


@dataclass(frozen=True)
class MergeField:
    family: str  # Input, RelatedList, Flow, Apex, EinsteinSearch
    reference: str  # Case.Subject, Case.CaseComments.Records, CaseSummaryGrounding.Prompt, ...
    raw: str

    @property
    def field_name(self) -> str | None:
        """For an Input family: the field after the reference name (Case.Contact.Name -> Contact.Name)."""
        if self.family != "Input":
            return None
        parts = self.reference.split(".", 1)
        return parts[1] if len(parts) == 2 else None

    @property
    def provider(self) -> str | None:
        if self.family in ("Flow", "Apex", "EinsteinSearch"):
            return self.reference.split(".", 1)[0]
        return None


@dataclass
class TemplateInput:
    api_name: str
    definition: str
    reference_name: str
    required: bool


@dataclass
class DataProvider:
    definition: str
    reference_name: str
    label: str


@dataclass
class TemplateVersion:
    identifier: str
    status: str
    primary_model: str
    response_format: str
    content: str
    inputs: list[TemplateInput]
    providers: list[DataProvider]
    merge_fields: list[MergeField] = field(default_factory=list)

    @property
    def fields(self) -> list[str]:
        """The Input fields the contract names, in content order, deduplicated."""
        seen: list[str] = []
        for m in self.merge_fields:
            name = m.field_name
            if name and name not in seen:
                seen.append(name)
        return seen

    @property
    def families(self) -> set[str]:
        return {m.family for m in self.merge_fields}

    def has(self, family: str) -> bool:
        return any(m.family == family for m in self.merge_fields)


@dataclass
class Template:
    path: str
    developer_name: str
    master_label: str
    type: str
    related_entity: str
    related_field: str
    active_version: str
    versions: dict[str, TemplateVersion]

    def version(self, identifier: str) -> TemplateVersion:
        if identifier not in self.versions:
            raise PrgError(f"{self.path}: no version {identifier!r}; versions are {', '.join(self.versions)}")
        return self.versions[identifier]


def _text(element: ET.Element, tag: str, path: str, required: bool = True) -> str:
    child = element.find(NS + tag)
    if child is None or child.text is None:
        if required:
            raise PrgError(f"{path}: <{tag}> is missing")
        return ""
    return child.text


def parse_merge_fields(content: str, families: list[str], path: str) -> list[MergeField]:
    found: list[MergeField] = []
    for match in MERGE.finditer(content):
        family, reference = match.group(1), match.group(2)
        if family not in families:
            raise PrgError(f"{path}: unknown merge-field family in {match.group(0)!r}; the policy accepts {', '.join(families)}")
        found.append(MergeField(family, reference, match.group(0)))
    return found


def read_template(path: Path, families: list[str]) -> Template:
    relative = str(path)
    try:
        root = ET.parse(path).getroot()
    except FileNotFoundError as exc:
        raise PrgError(f"template not found: {relative}") from exc
    except ET.ParseError as exc:
        raise PrgError(f"{relative}: malformed XML ({exc})") from exc
    if root.tag != NS + "GenAiPromptTemplate":
        raise PrgError(f"{relative}: root element is {root.tag}, not GenAiPromptTemplate")
    developer_name = _text(root, "developerName", relative, required=False) or path.name.split(".")[0]
    versions: dict[str, TemplateVersion] = {}
    for v in root.findall(NS + "templateVersions"):
        identifier = _text(v, "versionIdentifier", relative)
        if identifier in versions:
            raise PrgError(f"{relative}: versionIdentifier {identifier!r} appears twice")
        status = _text(v, "status", relative)
        if status not in ("Published", "Draft"):
            raise PrgError(f"{relative}: version {identifier}: status {status!r} is not Published or Draft")
        content = _text(v, "content", relative)
        inputs = [
            TemplateInput(
                api_name=_text(i, "apiName", relative),
                definition=_text(i, "definition", relative),
                reference_name=_text(i, "referenceName", relative),
                required=_text(i, "required", relative, required=False) == "true",
            )
            for i in v.findall(NS + "inputs")
        ]
        providers = [
            DataProvider(
                definition=_text(p, "definition", relative),
                reference_name=_text(p, "referenceName", relative),
                label=_text(p, "label", relative, required=False),
            )
            for p in v.findall(NS + "templateDataProviders")
        ]
        merge_fields = parse_merge_fields(content, families, f"{relative} version {identifier}")
        for m in merge_fields:
            if m.family == "Input":
                ref = m.reference.split(".", 1)[0]
                if ref not in {i.reference_name.split(":", 1)[-1] for i in inputs}:
                    raise PrgError(
                        f"{relative} version {identifier}: {m.raw} names input {ref!r}, which the version does not declare"
                    )
            if m.family in ("Flow", "Apex") and m.provider not in {p.reference_name for p in providers}:
                raise PrgError(
                    f"{relative} version {identifier}: {m.raw} names provider {m.provider!r}, which the version does not declare"
                )
        versions[identifier] = TemplateVersion(
            identifier=identifier,
            status=status,
            primary_model=_text(v, "primaryModel", relative, required=False),
            response_format=_text(v, "responseFormat", relative, required=False) or "Text",
            content=content,
            inputs=inputs,
            providers=providers,
            merge_fields=merge_fields,
        )
    if not versions:
        raise PrgError(f"{relative}: no <templateVersions>")
    active = _text(root, "activeVersionIdentifier", relative)
    if active not in versions:
        raise PrgError(f"{relative}: activeVersionIdentifier {active!r} names no version")
    if versions[active].status != "Published":
        raise PrgError(f"{relative}: the active version {active} must be Published, it is {versions[active].status}")
    return Template(
        path=relative,
        developer_name=developer_name,
        master_label=_text(root, "masterLabel", relative),
        type=_text(root, "type", relative),
        related_entity=_text(root, "relatedEntity", relative, required=False),
        related_field=_text(root, "relatedField", relative, required=False),
        active_version=active,
        versions=versions,
    )


def find_template(project_dir: Path, families: list[str], developer_name: str | None = None) -> Template:
    """The one template in the SFDX project (or the named one)."""
    folder = Path(project_dir) / "force-app" / "main" / "default" / "genAiPromptTemplates"
    files = sorted(folder.glob("*.genAiPromptTemplate-meta.xml"))
    if developer_name:
        files = [f for f in files if f.name.startswith(developer_name + ".")]
    if not files:
        raise PrgError(
            f"{folder}: no .genAiPromptTemplate-meta.xml file" + (f" named {developer_name}" if developer_name else "")
        )
    if len(files) > 1:
        raise PrgError(f"{folder}: {len(files)} templates; name one with --template")
    return read_template(files[0], families)
