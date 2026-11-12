"""The export readers: cases, comments, chunks, and what they refuse."""

from __future__ import annotations

import json

import pytest

from prg.exit_codes import PrgError
from prg.exports import read_exports

from .conftest import FIXTURE
from .helpers import edit


def test_the_fixture_exports_hold_two_hundred_cases_their_comments_and_three_chunks_each():
    e = read_exports(FIXTURE / "data")
    assert len(e.cases) == 200
    assert e.comments_total == sum(len(c.comments) for c in e.cases.values())
    assert e.chunks_total == 600 and all(len(c.chunks) == 3 for c in e.cases.values())
    assert "Contact.Name" in e.columns and "Amount__c" in e.columns


def test_every_case_has_at_least_two_comments_and_chunks_sorted_by_rank():
    e = read_exports(FIXTURE / "data")
    for c in e.cases.values():
        assert len(c.comments) >= 2
        assert [k.rank for k in c.chunks] == [1, 2, 3]


def test_a_missing_case_is_refused_by_id():
    e = read_exports(FIXTURE / "data")
    with pytest.raises(PrgError, match="no case 'nope'"):
        e.case("nope")


def test_a_case_value_is_none_for_an_unknown_column():
    e = read_exports(FIXTURE / "data")
    assert next(iter(e.cases.values())).value("Rating") is None


def test_a_missing_export_directory_is_refused(tmp_path):
    with pytest.raises(PrgError, match="export not found"):
        read_exports(tmp_path)


def test_a_case_file_without_an_id_column_is_refused(mini):
    edit(mini / "data" / "Case.csv", "Id,Subject", "Ident,Subject")
    with pytest.raises(PrgError, match="column 'Id' is missing"):
        read_exports(mini / "data")


def test_a_duplicate_case_id_is_refused(mini):
    edit(mini / "data" / "Case.csv", "500000000000002AAA", "500000000000001AAA")
    with pytest.raises(PrgError, match="appears twice"):
        read_exports(mini / "data")


def test_an_empty_case_id_is_refused_with_the_row(mini):
    edit(mini / "data" / "Case.csv", "500000000000002AAA", "")
    with pytest.raises(PrgError, match="row 3 has no Id"):
        read_exports(mini / "data")


def test_a_comment_on_an_unknown_case_is_refused(mini):
    edit(mini / "data" / "CaseComment.csv", "500000000000002AAA", "500000000000099AAA")
    with pytest.raises(PrgError, match="which is not a case"):
        read_exports(mini / "data")


def test_a_chunk_line_that_is_not_json_is_refused_with_the_line(mini):
    p = mini / "data" / "chunks.jsonl"
    p.write_text(p.read_text(encoding="utf-8") + "{not json\n", encoding="utf-8")
    with pytest.raises(PrgError, match="line 5 is not valid JSON"):
        read_exports(mini / "data")


def test_a_chunk_without_a_required_key_is_refused(mini):
    p = mini / "data" / "chunks.jsonl"
    p.write_text(json.dumps({"caseId": "500000000000001AAA", "rank": 1}) + "\n", encoding="utf-8")
    with pytest.raises(PrgError, match="lacks 'chunkId'"):
        read_exports(mini / "data")


def test_a_chunk_for_an_unknown_case_is_refused(mini):
    p = mini / "data" / "chunks.jsonl"
    edit(p, "500000000000002AAA", "500000000000098AAA")
    with pytest.raises(PrgError, match="not in the export"):
        read_exports(mini / "data")


def test_blank_chunk_lines_are_skipped_and_the_file_is_optional(mini):
    p = mini / "data" / "chunks.jsonl"
    p.write_text("\n" + p.read_text(encoding="utf-8") + "\n\n", encoding="utf-8")
    assert read_exports(mini / "data").chunks_total == 4
    p.unlink()
    assert read_exports(mini / "data").chunks_total == 0
