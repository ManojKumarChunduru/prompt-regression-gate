"""A small corpus written to a temporary directory, for boundary and verdict tests.

The committed fixture is large and fixed; these tests need a corpus they can bend one element at a
time. `write_corpus` writes the smallest project that passes validation (one template with two
versions, four cases with comments and chunks, generations for both versions, three reviewers and
an order), and the `edit` helpers change one file before the gate reads it.
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAMMAR = ROOT / "fixture" / "policy" / "claim-grammar.json"
NS = "http://soap.sforce.com/2006/04/metadata"
XML = '<?xml version="1.0" encoding="UTF-8"?>\n'

CASES = [
    {
        "Id": "500000000000001AAA",
        "Subject": "Aero 2 stops charging",
        "Description": "Customer Priya Natarajan reports the Aero 2 stops charging since 2026-02-01.",
        "Priority": "High",
        "Status": "Working",
        "Type": "Problem",
        "Product__c": "Aero 2",
        "Contact.Name": "Priya Natarajan",
        "Amount__c": "240.00",
        "CreatedDate": "2026-02-10",
    },
    {
        "Id": "500000000000002AAA",
        "Subject": "Pulse Band miscounts steps",
        "Description": "Customer Daniel Okafor reports the Pulse Band miscounts steps since 2026-03-03.",
        "Priority": "Low",
        "Status": "New",
        "Type": "Question",
        "Product__c": "Pulse Band",
        "Contact.Name": "Daniel Okafor",
        "Amount__c": "89.00",
        "CreatedDate": "2026-03-05",
    },
    {
        "Id": "500000000000003AAA",
        "Subject": "Nimbus Hub drops the wifi hourly",
        "Description": "Customer Mei Sato reports the Nimbus Hub drops the wifi hourly since 2026-04-01.",
        "Priority": "Medium",
        "Status": "Escalated",
        "Type": "Problem",
        "Product__c": "Nimbus Hub",
        "Contact.Name": "Mei Sato",
        "Amount__c": "199.00",
        "CreatedDate": "2026-04-02",
    },
    {
        "Id": "500000000000004AAA",
        "Subject": "Orbit Cam records without audio",
        "Description": "Customer Tomas Novak reports the Orbit Cam records without audio since 2026-05-01.",
        "Priority": "High",
        "Status": "Closed",
        "Type": "Problem",
        "Product__c": "Orbit Cam",
        "Contact.Name": "Tomas Novak",
        "Amount__c": "310.00",
        "CreatedDate": "2026-05-03",
    },
]
COMMENTS = [
    {
        "Id": "00a000000000001AAA",
        "ParentId": "500000000000001AAA",
        "CommentBody": "Confirmed with the customer: the Aero 2 stops charging since 2026-02-01. Serial SN-48213.",
        "CreatedDate": "2026-02-10",
    },
    {
        "Id": "00a000000000002AAA",
        "ParentId": "500000000000001AAA",
        "CommentBody": "Offered a refund of $240.00.",
        "CreatedDate": "2026-02-11",
    },
    {
        "Id": "00a000000000003AAA",
        "ParentId": "500000000000002AAA",
        "CommentBody": "Scheduled a callback on 2026-03-09.",
        "CreatedDate": "2026-03-06",
    },
    {
        "Id": "00a000000000004AAA",
        "ParentId": "500000000000003AAA",
        "CommentBody": "Escalated to tier 2 on 2026-04-03.",
        "CreatedDate": "2026-04-03",
    },
    {
        "Id": "00a000000000005AAA",
        "ParentId": "500000000000004AAA",
        "CommentBody": "Customer confirmed order ORD-77001 and asked for a replacement.",
        "CreatedDate": "2026-05-04",
    },
]
CHUNKS = [
    {
        "caseId": "500000000000001AAA",
        "rank": 1,
        "chunkId": "chunk-aero-2-01",
        "article": "Aero 2 support article",
        "product": "Aero 2",
        "text": "Aero 2 units carry a 24-month warranty from the purchase date.",
        "score": 0.9,
    },
    {
        "caseId": "500000000000001AAA",
        "rank": 2,
        "chunkId": "chunk-pulse-band-01",
        "article": "Pulse Band support article",
        "product": "Pulse Band",
        "text": "Pulse Band straps are replaced free within 12 months.",
        "score": 0.8,
    },
    {
        "caseId": "500000000000001AAA",
        "rank": 3,
        "chunkId": "chunk-general-01",
        "article": "General support article",
        "product": "",
        "text": "A refund takes 10 days to reach the original card.",
        "score": 0.7,
    },
    {
        "caseId": "500000000000002AAA",
        "rank": 1,
        "chunkId": "chunk-pulse-band-01",
        "article": "Pulse Band support article",
        "product": "Pulse Band",
        "text": "Pulse Band straps are replaced free within 12 months.",
        "score": 0.9,
    },
]
V1 = """Summarize the case.
Subject: {!$Input:Case.Subject}
Description: {!$Input:Case.Description}
Priority: {!$Input:Case.Priority}
Status: {!$Input:Case.Status}
Product: {!$Input:Case.Product__c}
Customer: {!$Input:Case.Contact.Name}
Amount: {!$Input:Case.Amount__c}
Comments:
{!$RelatedList:Case.CaseComments.Records}"""
V2 = V1 + "\nFacts: {!$Apex:Grounder.Prompt}\nKnowledge:\n{!$EinsteinSearch:Retriever.Results}"


def template_xml(versions: list[tuple[str, str, str]], active: str = "v1", providers_for: tuple[str, ...] = ("v2",)) -> str:
    parts = [
        f'{XML}<GenAiPromptTemplate xmlns="{NS}">',
        f"    <activeVersionIdentifier>{active}</activeVersionIdentifier>",
        "    <developerName>Mini_Summary</developerName>",
        "    <masterLabel>Mini Summary</masterLabel>",
        "    <relatedEntity>Case</relatedEntity>",
    ]
    for identifier, status, content in versions:
        parts += [
            "    <templateVersions>",
            f"        <content>{content}</content>",
            "        <inputs><apiName>Case</apiName><definition>SOBJECT://Case</definition><referenceName>Input:Case</referenceName><required>true</required></inputs>",
            "        <primaryModel>sfdc_ai__DefaultOpenAIGPT4OmniMini</primaryModel>",
            f"        <status>{status}</status>",
        ]
        if identifier in providers_for:
            parts.append(
                "        <templateDataProviders><definition>apex://Grounder</definition><label>Grounder</label><referenceName>Grounder</referenceName></templateDataProviders>"
            )
        parts += [f"        <versionIdentifier>{identifier}</versionIdentifier>", "    </templateVersions>"]
    parts += ["    <type>einstein_gpt__fieldCompletion</type>", "</GenAiPromptTemplate>", ""]
    return "\n".join(parts)


SUMMARIES = {
    "v1": {
        "500000000000001AAA": "Priya Natarajan reported that the Aero 2 stops charging since 2026-02-01. The case is High priority and the status is Working. The agent offered a refund of $240.00.",
        "500000000000002AAA": "Daniel Okafor reported that the Pulse Band miscounts steps since 2026-03-03. The case is Low priority and the status is New. A callback is scheduled for 2026-03-09.",
        "500000000000003AAA": "Mei Sato reported that the Nimbus Hub drops the wifi hourly since 2026-04-01. The case is Medium priority and the status is Escalated. The case was escalated to tier 2 on 2026-04-03.",
        "500000000000004AAA": "Tomas Novak reported that the Orbit Cam records without audio since 2026-05-01. The case is High priority and the status is Closed. The customer confirmed order ORD-77001 and asked for a replacement.",
    },
    "v2": {
        "500000000000001AAA": "Priya Natarajan contacted support because the Aero 2 stops charging since 2026-02-01. It is a Low priority case and the status is currently Working. The agent offered a refund of $420.00. The knowledge base notes that Pulse Band straps are replaced free within 12 months. The customer sounds frustrated and wants a quick resolution.",
        "500000000000002AAA": "Daniel Okafor contacted support because the Pulse Band miscounts steps since 2026-03-03. It is a Low priority case and the status is currently New. A replacement unit was shipped under RMA-55001 on 2026-03-20. The knowledge base notes that Pulse Band straps are replaced free within 12 months.",
        "500000000000003AAA": "Mei Sato contacted support because the Nimbus Hub drops the wifi hourly since 2026-04-01. It is a Medium priority case and the status is currently Escalated.",
        "500000000000004AAA": "Tomas Novak contacted support because the Orbit Cam records without audio since 2026-05-01. It is a High priority case and the status is currently Closed. The customer confirmed order ORD-77001 and asked for a replacement.",
    },
}
ORDER = ["500000000000003AAA", "500000000000001AAA", "500000000000004AAA", "500000000000002AAA"]
SCORES = {
    "reviewer_a": {"v1": [3, 3, 4, 3], "v2": [4, 4, 5, 4]},
    "reviewer_b": {"v1": [2, 3, 3, 3], "v2": [3, 4, 3, 4]},
    "reviewer_c": {"v1": [3, 4, 4, 3], "v2": [4, 5, 4, 4]},
}


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in columns})


def write_corpus(
    root: Path, versions: list[tuple[str, str, str]] | None = None, active: str = "v1", with_reviews: bool = True
) -> Path:
    """Writes the small corpus under root/mini and returns that project directory."""
    from prg.exports import read_exports
    from prg.generations import resolve, write_generation
    from prg.metadata import read_template
    from prg.policy import load_policy

    project = root / "mini"
    folder = project / "force-app" / "main" / "default" / "genAiPromptTemplates"
    folder.mkdir(parents=True)
    versions = versions or [("v1", "Published", V1), ("v2", "Draft", V2)]
    (folder / "Mini_Summary.genAiPromptTemplate-meta.xml").write_text(template_xml(versions, active), encoding="utf-8")
    (project / "policy").mkdir()
    shutil.copy(GRAMMAR, project / "policy" / "claim-grammar.json")
    (project / "policy" / "gate-policy.json").write_text(
        json.dumps({"draws": {"value": {"count": 20, "size": 3, "seed": 1}, "reason": "small"}}), encoding="utf-8"
    )
    data = project / "data"
    write_csv(data / "Case.csv", CASES, list(CASES[0].keys()))
    write_csv(data / "CaseComment.csv", COMMENTS, ["Id", "ParentId", "CommentBody", "CreatedDate"])
    (data / "chunks.jsonl").write_text("".join(json.dumps(c) + "\n" for c in CHUNKS), encoding="utf-8")
    policy = load_policy(project / "policy" / "gate-policy.json")
    template = read_template(folder / "Mini_Summary.genAiPromptTemplate-meta.xml", policy.merge_field_families)
    exports = read_exports(data)
    for identifier in template.versions:
        if identifier not in SUMMARIES:
            continue
        for case_id, text in SUMMARIES[identifier].items():
            prompt = resolve(template.version(identifier), exports.case(case_id), exports, policy)
            write_generation(
                project / "generations" / identifier / f"{case_id}.json",
                "Mini_Summary",
                identifier,
                case_id,
                text,
                prompt,
                f"req-{identifier}-{case_id[-6:-3]}",
            )
    if with_reviews:
        reviews = project / "reviews"
        reviews.mkdir()
        (reviews / "order.txt").write_text("\n".join(ORDER) + "\n", encoding="utf-8")
        for reviewer, by_version in SCORES.items():
            rows = []
            for index, case_id in enumerate(ORDER):
                for identifier, scores in by_version.items():
                    rows.append(
                        {
                            "caseId": case_id,
                            "version": identifier,
                            "score": scores[index],
                            "flagged": "yes"
                            if (reviewer, case_id, identifier) == ("reviewer_a", "500000000000001AAA", "v2")
                            else "no",
                            "note": "",
                        }
                    )
            write_csv(reviews / f"{reviewer}.csv", rows, ["caseId", "version", "score", "flagged", "note"])
    return project


def paths(project: Path) -> dict:
    return {
        "project_dir": project,
        "data_dir": project / "data",
        "generations_dir": project / "generations",
        "reviews_dir": project / "reviews",
        "policy_path": project / "policy" / "gate-policy.json",
        "grammar_path": project / "policy" / "claim-grammar.json",
    }


def edit(path: Path, old: str, new: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not in {path}"
    path.write_text(text.replace(old, new, count), encoding="utf-8")


def set_summary(project: Path, version: str, case_id: str, text: str) -> None:
    """Rewrites one generation's text, keeping its resolved prompt."""
    path = project / "generations" / version / f"{case_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["generations"][0]["text"] = text
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def set_score(project: Path, reviewer: str, case_id: str, version: str, score: str) -> None:
    path = project / "reviews" / f"{reviewer}.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
    for row in rows:
        if row["caseId"] == case_id and row["version"] == version:
            row["score"] = score
    write_csv(path, rows, ["caseId", "version", "score", "flagged", "note"])


def refresh_prompts(project: Path) -> None:
    """Re-resolves every committed prompt after an export or template edit, so the drift check stays green."""
    from prg.exports import read_exports
    from prg.generations import resolve
    from prg.metadata import find_template
    from prg.policy import load_policy

    policy = load_policy(project / "policy" / "gate-policy.json")
    template = find_template(project, policy.merge_field_families)
    exports = read_exports(project / "data")
    for folder in (project / "generations").iterdir():
        version = template.version(folder.name)
        for path in folder.glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["prompt"] = resolve(version, exports.case(path.stem), exports, policy)
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
