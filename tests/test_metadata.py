"""The template reader and the grounding contract, with every refusal named."""

from __future__ import annotations

import pytest

from prg.exit_codes import PrgError
from prg.metadata import find_template, parse_merge_fields, read_template

from .conftest import FIXTURE
from .helpers import V1, V2, edit, template_xml

FAMILIES = ["Input", "RelatedList", "Flow", "Apex", "EinsteinSearch"]
TEMPLATE = FIXTURE / "force-app" / "main" / "default" / "genAiPromptTemplates" / "Case_Summary.genAiPromptTemplate-meta.xml"


def test_the_fixture_template_has_three_versions_with_v1_active_and_published():
    t = read_template(TEMPLATE, FAMILIES)
    assert list(t.versions) == ["v1", "v2", "v3"]
    assert t.active_version == "v1" and t.versions["v1"].status == "Published"
    assert t.versions["v2"].status == "Draft" and t.versions["v3"].status == "Draft"
    assert t.type == "einstein_gpt__fieldCompletion" and t.related_entity == "Case" and t.related_field == "Case.Case_Summary__c"


def test_the_fixture_contract_names_nine_fields_in_content_order():
    t = read_template(TEMPLATE, FAMILIES)
    assert t.versions["v1"].fields == [
        "Subject",
        "Description",
        "Priority",
        "Status",
        "Type",
        "Product__c",
        "Contact.Name",
        "Amount__c",
        "CreatedDate",
    ]


def test_v1_and_v2_share_a_contract_and_v3_adds_the_provider_and_the_retriever():
    t = read_template(TEMPLATE, FAMILIES)
    assert t.versions["v1"].fields == t.versions["v2"].fields == t.versions["v3"].fields
    assert t.versions["v1"].families == t.versions["v2"].families == {"Input", "RelatedList"}
    assert t.versions["v3"].families == {"Input", "RelatedList", "Apex", "EinsteinSearch"}
    assert [p.reference_name for p in t.versions["v3"].providers] == ["CaseSummaryGrounding"]


def test_a_merge_field_keeps_its_family_reference_and_raw_text():
    fields = parse_merge_fields("x {!$Input:Case.Contact.Name} y {!$Apex:G.Prompt}", FAMILIES, "t")
    assert [(m.family, m.reference, m.raw) for m in fields] == [
        ("Input", "Case.Contact.Name", "{!$Input:Case.Contact.Name}"),
        ("Apex", "G.Prompt", "{!$Apex:G.Prompt}"),
    ]
    assert fields[0].field_name == "Contact.Name" and fields[0].provider is None
    assert fields[1].field_name is None and fields[1].provider == "G"


def test_an_input_reference_without_a_field_has_no_field_name():
    (m,) = parse_merge_fields("{!$Input:Case}", FAMILIES, "t")
    assert m.field_name is None


def test_an_unknown_merge_field_family_is_refused_with_the_expression_named():
    with pytest.raises(PrgError, match=r"\{!\$Foo:Bar\}"):
        parse_merge_fields("{!$Foo:Bar}", FAMILIES, "t")


def test_the_version_accessor_names_the_versions_when_one_is_missing():
    t = read_template(TEMPLATE, FAMILIES)
    with pytest.raises(PrgError, match="v1, v2, v3"):
        t.version("v9")


def test_find_template_finds_the_one_template_and_refuses_a_wrong_name():
    assert find_template(FIXTURE, FAMILIES).developer_name == "Case_Summary"
    assert find_template(FIXTURE, FAMILIES, "Case_Summary").developer_name == "Case_Summary"
    with pytest.raises(PrgError, match="named Nope"):
        find_template(FIXTURE, FAMILIES, "Nope")


def test_find_template_refuses_a_project_with_two_templates(mini):
    folder = mini / "force-app" / "main" / "default" / "genAiPromptTemplates"
    (folder / "Other.genAiPromptTemplate-meta.xml").write_text(template_xml([("v1", "Published", V1)]), encoding="utf-8")
    with pytest.raises(PrgError, match="2 templates"):
        find_template(mini, FAMILIES)
    assert find_template(mini, FAMILIES, "Other").developer_name == "Mini_Summary"


def test_find_template_refuses_an_empty_folder(tmp_path):
    with pytest.raises(PrgError, match="no .genAiPromptTemplate-meta.xml"):
        find_template(tmp_path, FAMILIES)


def test_a_missing_template_file_is_refused_by_path(tmp_path):
    with pytest.raises(PrgError, match="template not found"):
        read_template(tmp_path / "nope.xml", FAMILIES)


def test_malformed_xml_is_refused_with_the_parser_message(tmp_path):
    p = tmp_path / "bad.xml"
    p.write_text("<GenAiPromptTemplate><templateVersions>", encoding="utf-8")
    with pytest.raises(PrgError, match="malformed XML"):
        read_template(p, FAMILIES)


def test_a_wrong_root_element_is_refused(tmp_path):
    p = tmp_path / "bad.xml"
    p.write_text('<?xml version="1.0"?><Flow xmlns="http://soap.sforce.com/2006/04/metadata"/>', encoding="utf-8")
    with pytest.raises(PrgError, match="not GenAiPromptTemplate"):
        read_template(p, FAMILIES)


def _mini_template(mini):
    return mini / "force-app" / "main" / "default" / "genAiPromptTemplates" / "Mini_Summary.genAiPromptTemplate-meta.xml"


def test_a_version_whose_input_is_not_declared_is_refused(mini):
    path = _mini_template(mini)
    edit(path, "{!$Input:Case.Subject}", "{!$Input:Account.Name}")
    with pytest.raises(PrgError, match="names input 'Account'"):
        read_template(path, FAMILIES)


def test_a_provider_the_version_does_not_declare_is_refused(mini):
    path = _mini_template(mini)
    edit(path, "{!$Apex:Grounder.Prompt}", "{!$Apex:Other.Prompt}")
    with pytest.raises(PrgError, match="names provider 'Other'"):
        read_template(path, FAMILIES)


def test_an_active_version_that_is_a_draft_is_refused(mini):
    path = _mini_template(mini)
    edit(path, "<status>Published</status>", "<status>Draft</status>")
    with pytest.raises(PrgError, match="must be Published"):
        read_template(path, FAMILIES)


def test_an_active_identifier_naming_no_version_is_refused(mini):
    path = _mini_template(mini)
    edit(path, "<activeVersionIdentifier>v1</activeVersionIdentifier>", "<activeVersionIdentifier>v7</activeVersionIdentifier>")
    with pytest.raises(PrgError, match="names no version"):
        read_template(path, FAMILIES)


def test_a_duplicate_version_identifier_is_refused(mini):
    path = _mini_template(mini)
    edit(path, "<versionIdentifier>v2</versionIdentifier>", "<versionIdentifier>v1</versionIdentifier>")
    with pytest.raises(PrgError, match="appears twice"):
        read_template(path, FAMILIES)


def test_an_unknown_status_is_refused(mini):
    path = _mini_template(mini)
    edit(path, "<status>Draft</status>", "<status>Archived</status>")
    with pytest.raises(PrgError, match="not Published or Draft"):
        read_template(path, FAMILIES)


def test_a_missing_required_element_is_refused_by_tag(mini):
    path = _mini_template(mini)
    edit(path, "<masterLabel>Mini Summary</masterLabel>", "")
    with pytest.raises(PrgError, match="<masterLabel> is missing"):
        read_template(path, FAMILIES)


def test_a_template_with_no_versions_is_refused(tmp_path):
    p = tmp_path / "t.xml"
    p.write_text(template_xml([]), encoding="utf-8")
    with pytest.raises(PrgError, match="no <templateVersions>"):
        read_template(p, FAMILIES)


def test_the_developer_name_falls_back_to_the_file_name(tmp_path):
    p = tmp_path / "Fallback.genAiPromptTemplate-meta.xml"
    p.write_text(
        template_xml([("v1", "Published", V1)]).replace("    <developerName>Mini_Summary</developerName>\n", ""), encoding="utf-8"
    )
    assert read_template(p, FAMILIES).developer_name == "Fallback"


def test_the_response_format_defaults_to_text_when_absent():
    t = read_template(TEMPLATE, FAMILIES)
    assert t.versions["v1"].response_format == "MarkDown"
    assert read_template(_mini_path(), FAMILIES).versions["v1"].response_format == "Text"


def _mini_path():
    import tempfile
    from pathlib import Path

    d = Path(tempfile.mkdtemp())
    p = d / "Mini.genAiPromptTemplate-meta.xml"
    p.write_text(template_xml([("v1", "Published", V1), ("v2", "Draft", V2)]), encoding="utf-8")
    return p
