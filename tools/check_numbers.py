"""Fails the build when a document quotes a figure the code no longer produces.

Reads docs/metrics.json (written by tools/collect_metrics.py) and every checked document. For each
metric, at least one anchor phrase with the current value must appear somewhere (else GAP), and no
anchor phrase may appear with a different value (STALE, with file and line). A phrase may name other
metrics as {m:key}, which pins a table cell by its neighbours; the stale check turns only the {} into
a number pattern. The banner's text nodes are checked with their own patterns. Finally the reverse
scan reports every number in prose that matches no metric value (UNANCHORED), excluding fenced code,
inline code, URLs, HTML tags, numbers glued to a hyphen or a word, and an allowlist that carries a
reason per entry.

Exit 0 when clean, 1 otherwise. `make verify` runs it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
payload = json.loads((ROOT / "docs" / "metrics.json").read_text(encoding="utf-8"))
metrics: dict = payload["metrics"]
anchors: dict = payload["anchors"]
documents: list[str] = payload["checked_documents"]
banner: dict | None = payload.get("banner")

# Numbers that appear in prose and are not measurements. One reason each.
ALLOWED_UNANCHORED: dict[str, str] = {
    "0": "zero in prose (0 runtime dependencies, exit 0, a flag off)",
    "1": "a count of one in prose (one page, one record, a floor of 1 in N, exit 1)",
    "2": "a count of two in prose (two pages, exit 2)",
    "3": "three readers, three page families, exit 3",
    "4": "four criteria operations, four pinned stages of the build",
    "5": "the five ADRs and five experiments",
    "6": "six page families",
    "7": "a numbered item in ADR-005",
    "8": "a numbered item in ADR-005",
    "9": "a numbered item in ADR-005",
    "200": "the UserRecordAccess query limit per call, a documented constant",
    "2026": "the year in the licence and the dates",
    "3.11": "the oldest Python the package supports",
    "3.13": "the newest Python in the CI matrix",
    "001": "ADR number in a link title",
    "002": "ADR number in a link title",
    "003": "ADR number in a link title",
    "004": "ADR number in a link title",
    "005": "ADR number in a link title",
    "62.0": "the fixture's API version",
}

NUMBER = r"(\d+(?:,\d{3})*(?:\.\d+)?)"


def formatted(value: object) -> str:
    return str(value)


def same_number(a: str, b: str) -> bool:
    return float(str(a).replace(",", "")) == float(str(b).replace(",", ""))


def compile_phrase(phrase: str, slot: str) -> str:
    """Literal text escaped; {m:key} becomes that metric's value; {} becomes `slot`."""
    source = ""
    for part in re.split(r"(\{m:[a-z0-9_]+\}|\{\})", phrase):
        if part == "{}":
            source += slot
        elif part.startswith("{m:"):
            key = part[3:-1]
            if key not in metrics:
                raise SystemExit(f"check_numbers: anchor names unknown metric {key}")
            source += re.escape(formatted(metrics[key]))
        else:
            source += re.escape(part)
    return source


class Document:
    def __init__(self, relative: str):
        self.path = relative
        self.text = (ROOT / relative).read_text(encoding="utf-8")
        self.lines = self.text.split("\n")


problems: list[str] = []
docs: list[Document] = []
for relative in documents:
    if (ROOT / relative).exists():
        docs.append(Document(relative))
    else:
        problems.append(f"MISSING {relative}")

anchored = 0
for key, phrases in anchors.items():
    value = formatted(metrics[key])
    found = False
    for phrase in phrases:
        exact = re.compile(compile_phrase(phrase, re.escape(value)))
        stale = re.compile(compile_phrase(phrase, NUMBER))
        for doc in docs:
            if exact.search(doc.text):
                found = True
            for index, line in enumerate(doc.lines, start=1):
                for match in stale.finditer(line):
                    if not same_number(match.group(1), value):
                        problems.append(f'STALE {doc.path}:{index}: "{match.group(0)}" but {key} is {value}')
    if found:
        anchored += 1
    else:
        alternatives = ", ".join(f'"{p}"' for p in phrases)
        problems.append(f"GAP {key} = {value}: none of {alternatives} found in any checked document")

if banner:
    svg_path = ROOT / banner["path"]
    if not svg_path.exists():
        problems.append(f"MISSING {banner['path']}")
    else:
        text_only = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", svg_path.read_text(encoding="utf-8")))
        for key, pattern in banner["figures"].items():
            value = formatted(metrics[key])
            if not re.search(compile_phrase(pattern, re.escape(value)), text_only):
                problems.append(f'GAP banner: "{pattern.replace("{}", value)}" not in {banner["path"]}')
            for match in re.finditer(compile_phrase(pattern, NUMBER), text_only):
                if not same_number(match.group(1), value):
                    problems.append(f'STALE banner: "{match.group(0)}" but {key} is {value}')

# Reverse scan: numbers in prose that match no metric value.
metric_values = {str(v).replace(",", "") for v in metrics.values()}
unanchored: list[str] = []
for doc in docs:
    prose = re.sub(r"```[\s\S]*?```", lambda m: re.sub(r"[^\n]", "", m.group(0)), doc.text)
    prose = re.sub(r"`[^`\n]*`", lambda m: " " * len(m.group(0)), prose)
    prose = re.sub(r"https?://\S+", lambda m: " " * len(m.group(0)), prose)
    prose = re.sub(r"<[^>\n]+>", lambda m: " " * len(m.group(0)), prose)
    for index, line in enumerate(prose.split("\n"), start=1):
        for match in re.finditer(r"(?<![\w.-])(\d+(?:,\d{3})*(?:\.\d+)?)(?![\w-])", line):
            raw = match.group(1)
            clean = raw.replace(",", "")
            if clean in metric_values or raw in ALLOWED_UNANCHORED or clean in ALLOWED_UNANCHORED:
                continue
            unanchored.append(f'UNANCHORED {doc.path}:{index}: {raw} in "{doc.lines[index - 1].strip()[:90]}"')
problems.extend(unanchored)

counts = {
    "gap": sum(p.startswith("GAP") for p in problems),
    "stale": sum(p.startswith("STALE") for p in problems),
    "missing": sum(p.startswith("MISSING") for p in problems),
    "unanchored": len(unanchored),
}
for problem in problems:
    print(problem)
print(
    f"check_numbers: {len(metrics)} metrics, {anchored} anchored, {len(docs)} documents{' plus the banner' if banner else ''}; "
    f"{counts['gap']} gaps, {counts['stale']} stale, {counts['missing']} missing, {counts['unanchored']} unanchored"
)
sys.exit(0 if not problems else 1)
