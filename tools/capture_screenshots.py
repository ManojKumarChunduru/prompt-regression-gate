"""Section-framed screenshots of the real HTML report, with the verdict badge read back.

Builds the report with the CLI first, so the screenshot can never be of a stale file. Frames by
heading id rather than pixel offset; fails if a heading is missing. Reads the computed style of
the verdict badge and fails if it is invisible, because the only thing in the pipeline that can
see pixels is this tool. The hidden pairs table is capped at its first screen and the cap is
recorded in the manifest. Writes a manifest with the readings.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from browser import playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "evidence"
OUT.mkdir(parents=True, exist_ok=True)
HTML = OUT / "report.html"

run = subprocess.run(
    [
        sys.executable,
        "-m",
        "sea.cli",
        "audit",
        "--project",
        "fixture",
        "--data",
        "fixture/data",
        "--policy",
        "fixture/policy/sharing-policy.json",
        "--html",
        str(HTML),
    ],
    cwd=ROOT,
    capture_output=True,
    text=True,
)
if run.returncode not in (0, 1, 2):
    print(f"capture_screenshots: sea audit failed with {run.returncode}\n{run.stderr}", file=sys.stderr)
    sys.exit(1)

# Framed by heading id. The hidden pairs table runs to 60 rows with their paths, so the first shot is capped in
# height (recorded in the manifest); a cap is not a pixel offset, and the shot still fails if a heading disappears.
SHOTS = [
    {"name": "report-hidden.png", "from": "header", "to": "objects", "maxHeight": 1500},
    {"name": "report-readers.png", "from": "objects", "to": "refusals", "maxHeight": None},
]

with playwright()() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1360, "height": 900}, device_scale_factor=1)
    page.goto(f"file://{HTML}")
    badge = page.evaluate(
        """() => {
          const el = document.querySelector('#verdict');
          if (!el) return null;
          const style = getComputedStyle(el);
          return { text: el.textContent, colour: style.color, background: style.backgroundColor,
                   visible: el.offsetWidth > 0 && el.offsetHeight > 0 };
        }"""
    )
    if badge is None or not badge["visible"] or badge["colour"] == badge["background"]:
        print(f"capture_screenshots: the verdict badge is missing or invisible: {badge}", file=sys.stderr)
        sys.exit(1)
    manifest = {"report": "docs/evidence/report.html", "generatedBy": "tools/capture_screenshots.py", "badge": badge, "shots": []}
    for shot in SHOTS:
        box = page.evaluate(
            """({from: start, to: end}) => {
              const a = document.getElementById(start);
              if (!a) return { error: `heading ${start} not found` };
              const top = a.getBoundingClientRect().top + window.scrollY;
              let bottom;
              if (end === null) bottom = document.documentElement.scrollHeight;
              else {
                const b = document.getElementById(end);
                if (!b) return { error: `heading ${end} not found` };
                bottom = b.getBoundingClientRect().top + window.scrollY;
              }
              return { x: 0, y: Math.max(0, top - 8), width: document.documentElement.clientWidth, height: bottom - top + 8 };
            }""",
            {"from": shot["from"], "to": shot["to"]},
        )
        if "error" in box:
            print(f"capture_screenshots: {box['error']}; the report changed shape", file=sys.stderr)
            sys.exit(1)
        capped = shot["maxHeight"] is not None and box["height"] > shot["maxHeight"]
        if capped:
            box["height"] = shot["maxHeight"]
        path = OUT / shot["name"]
        page.screenshot(path=str(path), full_page=True, clip=box)
        manifest["shots"].append(
            {
                "file": f"docs/evidence/{shot['name']}",
                "framedBy": [shot["from"], shot["to"] or "end of document"],
                "clip": box,
                "capped": capped,
                "maxHeight": shot["maxHeight"],
            }
        )
        print(f"capture_screenshots: {shot['name']} {round(box['width'])}x{round(box['height'])}")
    browser.close()

(OUT / "screenshots.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(f'capture_screenshots: badge reads "{badge["text"]}" {badge["colour"]} on {badge["background"]}')
