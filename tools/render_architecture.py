"""Renders the architecture diagram from the README's mermaid-source fence to a committed SVG.

Rules learned the hard way: htmlLabels off at both levels, or the SVG carries <foreignObject>
and fails to load as <img>; explicit width and height from the viewBox; an opaque background so
dark-theme readers can see it. Playwright plus mermaid.min.js is the stable path; mmdc is the
fallback. The run fails if <foreignObject> is present.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

from browser import find_mermaid, playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "assets" / "architecture.svg"

readme = (ROOT / "README.md").read_text(encoding="utf-8")
fence = re.search(r"```mermaid-source\n([\s\S]*?)```", readme)
if fence is None:
    print("render_architecture: no mermaid-source fence in README.md", file=sys.stderr)
    sys.exit(1)
source = fence.group(1)


def render_with_playwright(mermaid_path: Path) -> str:
    with playwright()() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content("<!doctype html><html><body></body></html>")
        page.add_script_tag(path=str(mermaid_path))
        svg = page.evaluate(
            """async (src) => {
              window.mermaid.initialize({
                startOnLoad: false, htmlLabels: false, theme: "neutral",
                flowchart: { htmlLabels: false, nodeSpacing: 40, rankSpacing: 60, curve: "basis" },
                themeVariables: { fontFamily: "Inter, Segoe UI, system-ui, sans-serif", fontSize: "14px" },
              });
              const { svg } = await window.mermaid.render("architecture", src);
              return svg;
            }""",
            source,
        )
        browser.close()
    return svg


def render_with_mmdc() -> str:
    config = ROOT / "docs" / "assets" / ".mermaid-config.json"
    config.write_text(json.dumps({"htmlLabels": False, "flowchart": {"htmlLabels": False}, "theme": "neutral"}))
    source_file = ROOT / "docs" / "assets" / ".architecture.mmd"
    source_file.write_text(source)
    subprocess.run(["mmdc", "-i", str(source_file), "-o", str(OUT), "-c", str(config), "-b", "white"], check=True)
    return OUT.read_text(encoding="utf-8")


mermaid_path = find_mermaid()
if mermaid_path is not None:
    svg = render_with_playwright(mermaid_path)
    method = f"playwright + {mermaid_path}"
elif shutil.which("mmdc"):
    svg = render_with_mmdc()
    method = "mmdc"
else:
    print("render_architecture: neither mermaid.min.js nor mmdc was found", file=sys.stderr)
    sys.exit(1)

if "<foreignObject" in svg:
    print("render_architecture: the SVG contains <foreignObject>; htmlLabels did not turn off", file=sys.stderr)
    sys.exit(1)

view_box = re.search(r'viewBox="([\d.\s-]+)"', svg)
if view_box is None:
    print("render_architecture: no viewBox on the rendered SVG", file=sys.stderr)
    sys.exit(1)
_, _, w, h = (float(v) for v in view_box.group(1).split())
width, height = math.ceil(w), math.ceil(h)


def rewrite_root(match: re.Match) -> str:
    attrs = re.sub(r'\s(width|height|style)="[^"]*"', "", match.group(1))
    return f'<svg{attrs} width="{width}" height="{height}"><rect x="0" y="0" width="100%" height="100%" fill="#ffffff"/>'


svg = re.sub(r"<svg([^>]*)>", rewrite_root, svg, count=1)
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(svg + "\n", encoding="utf-8")
(ROOT / "docs" / "assets" / "architecture.manifest.json").write_text(
    json.dumps(
        {"source": "README.md mermaid-source fence", "method": method, "width": width, "height": height, "foreignObject": False},
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
print(f"render_architecture: {OUT} ({width}x{height}) via {method}")
