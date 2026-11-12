"""Repository hygiene, enforced by the suite so a slip is caught before packaging.

Sweeps tracked and untracked files (git ls-files --cached --others --exclude-standard), so a file
that is not yet committed cannot exempt itself. Tests the repository, never the checkout: the
commit-author sweep reads the log, not the local config.
"""

import re
import subprocess
import tomllib
from pathlib import Path

from .conftest import ROOT

REPO = "ManojKumarChunduru/prompt-regression-gate"
AUTHOR = "Manoj Kumar Chunduru <hello.manojchunduru@gmail.com>"
TEXT_SUFFIXES = {
    ".py",
    ".json",
    ".jsonl",
    ".md",
    ".yml",
    ".yaml",
    ".xml",
    ".cls",
    ".svg",
    ".txt",
    ".html",
    ".css",
    ".csv",
    ".toml",
    "",
}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def text_files() -> list[Path]:
    listed = git("ls-files", "--cached", "--others", "--exclude-standard").splitlines()
    return [ROOT / p for p in listed if Path(p).suffix in TEXT_SUFFIXES and (ROOT / p).exists()]


EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)
# Assembled from parts so this file does not match its own sweep.
PLACEHOLDERS = re.compile(
    "|".join(["your" + "-handle", "YOUR" + "_HANDLE", "<" + "handle>", "example@" + "example", "your" + "name"]), re.I
)
ATTRIBUTION = re.compile(
    "(Co-Authored" + "-By|Generated " + "by|Generated " + "with)[^\n]*(Cla" + "ude|Anthro" + "pic|Chat" + "GPT|Copi" + "lot)",
    re.I,
)


def test_no_tracked_or_untracked_text_file_contains_an_em_dash_or_an_en_dash():
    offenders = [
        p
        for p in text_files()
        if EM_DASH in p.read_text(encoding="utf-8", errors="replace")
        or EN_DASH in p.read_text(encoding="utf-8", errors="replace")
    ]
    assert offenders == []


def test_every_commit_is_authored_by_the_candidate_alone_with_no_trailers_and_no_tool_name():
    authors = set(git("log", "--format=%an <%ae>").splitlines())
    assert authors == {AUTHOR}
    bodies = git("log", "--format=%B")
    for needle in (
        "Co-Authored" + "-By",
        "Co-authored" + "-by",
        "Generated" + "-By",
        "Session" + "-Id",
        "Cla" + "ude",
        "Anthro" + "pic",
        "Chat" + "GPT",
        "Copi" + "lot",
    ):
        assert needle not in bodies, f"commit messages mention {needle}"


def test_no_file_mentions_an_ai_tool_as_an_author_or_generator():
    offenders = [
        p for p in text_files() if "tests/" not in str(p) and ATTRIBUTION.search(p.read_text(encoding="utf-8", errors="replace"))
    ]
    assert offenders == []


def test_no_placeholder_handle_or_email_is_left_anywhere():
    offenders = [p for p in text_files() if PLACEHOLDERS.search(p.read_text(encoding="utf-8", errors="replace"))]
    assert offenders == []


def test_every_github_url_names_this_repository_exactly():
    offenders = []
    for path in text_files():
        for match in re.finditer(r"github\.com/([\w.-]+/[\w.-]+)", path.read_text(encoding="utf-8", errors="replace")):
            repo = match.group(1).removesuffix(".git")
            if repo != REPO:
                offenders.append(f"{path}: {repo}")
    assert offenders == []


def test_the_package_metadata_names_the_candidate_and_the_repository():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    (author,) = data["project"]["authors"]
    assert author == {"name": "Manoj Kumar Chunduru", "email": "hello.manojchunduru@gmail.com"}
    assert data["project"]["urls"]["Repository"] == f"https://github.com/{REPO}"


def test_the_licence_names_the_candidate():
    assert "Copyright (c) 2026 Manoj Kumar Chunduru" in (ROOT / "LICENSE").read_text()


def test_no_document_quotes_a_duration_as_a_figure():
    # The subject of this repository includes no time parameter, so the sweep runs unscoped.
    offenders = []
    for path in text_files():
        if path.suffix != ".md":
            continue
        text = re.sub(r"```[\s\S]*?```", "", path.read_text(encoding="utf-8", errors="replace"))
        for match in re.finditer(r"\b\d+(\.\d+)?\s?(ms|milliseconds|seconds|secs|minutes)\b", text, re.I):
            offenders.append(f"{path}: {match.group(0)}")
    assert offenders == []


def test_no_source_function_is_named_test_so_pytest_does_not_collect_it():
    offenders = []
    for path in (ROOT / "src").rglob("*.py"):
        for match in re.finditer(r"^def (test\w*)\(", path.read_text(), re.M):
            offenders.append(f"{path}: {match.group(1)}")
    assert offenders == []
