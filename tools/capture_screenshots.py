"""Section-framed screenshots of the real HTML report and the service's documentation page.

Builds the report with the CLI first, so the screenshot can never be of a stale file. Frames by
heading id rather than pixel offset; fails if a heading is missing. Reads the computed style of
the verdict badge and fails if it is invisible, because the only thing in the pipeline that can
see pixels is this tool. The bad-claims table is capped at its first screen and the cap is
recorded in the manifest. The api shot starts `prg serve` in a separate process on a free port
(the api extra must be installed), captures `/docs`, and stops it. Writes a manifest.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.request
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
        "prg.cli",
        "gate",
        "--project",
        "fixture",
        "--baseline",
        "v1",
        "--candidate",
        "v3",
        "--html",
        str(HTML),
        "--quiet",
    ],
    cwd=ROOT,
    capture_output=True,
    text=True,
)
if run.returncode not in (0, 1, 2):
    print(f"capture_screenshots: prg gate failed with {run.returncode}\n{run.stderr}", file=sys.stderr)
    sys.exit(1)

SHOTS = [
    {"name": "report-dimensions.png", "from": "header", "to": "claims", "maxHeight": None},
    {"name": "report-claims.png", "from": "claims", "to": None, "maxHeight": 1200},
]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


with playwright()() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1320, "height": 900}, device_scale_factor=1)
    page.goto(f"file://{HTML}")
    badge = page.evaluate(
        """() => {
          const el = document.querySelector('#badge');
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

    # The service's documentation page, from a separate process (the api extra must be installed).
    port = free_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "prg.cli", "serve", "--project", "fixture", "--port", str(port)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/versions", timeout=1) as response:
                    versions = json.loads(response.read().decode("utf-8"))
                    break
            except Exception:  # noqa: BLE001 (the server is still starting)
                if server.poll() is not None:
                    print(f"capture_screenshots: prg serve exited early\n{server.stderr.read()}", file=sys.stderr)
                    sys.exit(1)
                time.sleep(0.3)
        else:
            print("capture_screenshots: prg serve did not answer in time", file=sys.stderr)
            sys.exit(1)
        page.goto(f"http://127.0.0.1:{port}/docs")
        page.wait_for_selector("text=/gate", timeout=30000)
        page.wait_for_timeout(800)
        path = OUT / "api-docs.png"
        page.screenshot(path=str(path), full_page=False)
        manifest["shots"].append(
            {
                "file": "docs/evidence/api-docs.png",
                "framedBy": ["the service's /docs page"],
                "clip": {"width": 1320, "height": 900},
                "capped": True,
                "maxHeight": 900,
            }
        )
        manifest["api"] = {"route": "/versions", "template": versions["template"], "versions": sorted(versions["versions"])}
        print(
            f"capture_screenshots: api-docs.png from /docs on a free port ({versions['template']}, {len(versions['versions'])} versions)"
        )
    finally:
        server.terminate()
        server.wait(timeout=10)
    browser.close()

(OUT / "screenshots.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(f'capture_screenshots: badge reads "{badge["text"]}" {badge["colour"]} on {badge["background"]}')
