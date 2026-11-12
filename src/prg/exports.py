"""Reads the data exports: the cases, their comments and the retriever's results per case.

The exports are in the shape `sf data query --result-format csv` writes (one header row, the
relationship field `Contact.Name` as a dotted column) plus one JSONL file of retrieved chunks per
case, which is what the resolved prompt of a retriever version contains. The gate needs the data
because the grounding contract names fields and the summaries name values; metadata alone cannot
say whether "$240" was in the prompt.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

from .exit_codes import PrgError


@dataclass
class Comment:
    id: str
    parent_id: str
    body: str
    created: str


@dataclass
class Chunk:
    case_id: str
    rank: int
    chunk_id: str
    article: str
    product: str
    text: str
    score: float


@dataclass
class Case:
    id: str
    fields: dict[str, str]
    comments: list[Comment] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)

    def value(self, name: str) -> str | None:
        return self.fields.get(name)


@dataclass
class Exports:
    cases: dict[str, Case]
    columns: list[str]
    comments_total: int
    chunks_total: int

    def case(self, case_id: str) -> Case:
        if case_id not in self.cases:
            raise PrgError(f"no case {case_id!r} in the export")
        return self.cases[case_id]


def _read_csv(path: Path, required: tuple[str, ...]) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = list(reader.fieldnames or [])
            rows = list(reader)
    except FileNotFoundError as exc:
        raise PrgError(f"export not found: {path}") from exc
    for column in required:
        if column not in columns:
            raise PrgError(f"{path}: column {column!r} is missing (columns: {', '.join(columns)})")
    return columns, rows


def read_exports(data_dir: Path) -> Exports:
    data_dir = Path(data_dir)
    columns, case_rows = _read_csv(data_dir / "Case.csv", ("Id",))
    cases: dict[str, Case] = {}
    for index, row in enumerate(case_rows, start=2):
        case_id = row["Id"]
        if not case_id:
            raise PrgError(f"{data_dir / 'Case.csv'}: row {index} has no Id")
        if case_id in cases:
            raise PrgError(f"{data_dir / 'Case.csv'}: Id {case_id} appears twice")
        cases[case_id] = Case(id=case_id, fields=dict(row))
    _, comment_rows = _read_csv(data_dir / "CaseComment.csv", ("Id", "ParentId", "CommentBody", "CreatedDate"))
    comments_total = 0
    for index, row in enumerate(comment_rows, start=2):
        parent = row["ParentId"]
        if parent not in cases:
            raise PrgError(f"{data_dir / 'CaseComment.csv'}: row {index} names ParentId {parent}, which is not a case")
        cases[parent].comments.append(Comment(row["Id"], parent, row["CommentBody"], row["CreatedDate"]))
        comments_total += 1
    chunks_total = 0
    chunk_path = data_dir / "chunks.jsonl"
    if chunk_path.exists():
        for index, line in enumerate(chunk_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise PrgError(f"{chunk_path}: line {index} is not valid JSON ({exc.msg})") from exc
            for key in ("caseId", "rank", "chunkId", "article", "product", "text", "score"):
                if key not in raw:
                    raise PrgError(f"{chunk_path}: line {index} lacks {key!r}")
            if raw["caseId"] not in cases:
                raise PrgError(f"{chunk_path}: line {index} names case {raw['caseId']}, which is not in the export")
            cases[raw["caseId"]].chunks.append(
                Chunk(
                    raw["caseId"],
                    int(raw["rank"]),
                    raw["chunkId"],
                    raw["article"],
                    raw["product"],
                    raw["text"],
                    float(raw["score"]),
                )
            )
            chunks_total += 1
    for case in cases.values():
        case.chunks.sort(key=lambda c: c.rank)
    return Exports(cases=cases, columns=columns, comments_total=comments_total, chunks_total=chunks_total)
