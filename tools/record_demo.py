"""Records the demo: a replay of captured stdout, not a screen recording.

Runs each command, captures its real stdout, stderr, exit code and wall time; builds a
self-contained HTML player that types the command and reveals the captured output paced by the
measured wall time (clamped so a long command does not stall the replay, and the clamp is
recorded in the manifest); records the page with Playwright; transcodes with ffmpeg to an MP4
and a two-pass palette GIF (6 fps, 800 px wide, 32 colours) that stays under 5 MB. The output
stays `white-space: pre` and only the command line wraps, because wrapping the output triples the
GIF. Every line of terminal text in the video is captured output. None is hand-written.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from browser import playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "evidence"
OUT.mkdir(parents=True, exist_ok=True)

FIX = ["--project", "fixture", "--data", "fixture/data", "--policy", "fixture/policy/sharing-policy.json"]
FIX_TEXT = " ".join(FIX)
truth = json.loads((ROOT / "fixture" / "EXPECTED_ACCESS.json").read_text(encoding="utf-8"))
implicit = next(s for s in truth["scenarios"] if s["id"] == "S04")["pairs"]
# A pair whose only path is the implicit parent grant: the one the README quotes.
example = next(p for p in implicit if p["record"] == "001000000000075AAA")

SEGMENTS = [
    {
        "title": "Every reachable pair with its paths; the hidden pairs first",
        "command": f"sea audit {FIX_TEXT} --limit 8",
        "args": ["audit", *FIX, "--limit", "8"],
        "tailLines": 26,
    },
    {
        "title": "One pair: Read on an account through an opportunity rule, on no page",
        "command": f"sea explain {example['user']} {example['record']} {FIX_TEXT}",
        "args": ["explain", example["user"], example["record"], *FIX],
    },
    {"title": "What each single page would let a reviewer conclude", "command": f"sea pages {FIX_TEXT}", "args": ["pages", *FIX]},
    {
        "title": "The Finance group's bosses flag: what removing it loses",
        "command": f"sea without Finance {FIX_TEXT} --limit 6",
        "args": ["without", "Finance", *FIX, "--limit", "6"],
    },
    {
        "title": "The refused rule: what removing it decides",
        "command": f"sea without Project__c.High_Budget_Projects_To_Finance {FIX_TEXT} --limit 4",
        "args": ["without", "Project__c.High_Budget_Projects_To_Finance", *FIX, "--limit", "4"],
    },
    {
        "title": "The receipts: every figure in the docs checked against the code",
        "command": "python tools/check_numbers.py",
        "args": None,
    },
]

# Warm the import so the first segment does not pay for it.
subprocess.run([sys.executable, "-m", "sea.cli", "--help"], cwd=ROOT, capture_output=True)

MIN_SECONDS = 2.2
MAX_SECONDS = 7.0
captured = []
for segment in SEGMENTS:
    argv = (
        [sys.executable, "tools/check_numbers.py"]
        if segment["args"] is None
        else [sys.executable, "-m", "sea.cli", *segment["args"]]
    )
    started = time.perf_counter()
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
    wall = time.perf_counter() - started
    lines = (result.stdout + result.stderr).rstrip("\n").split("\n")
    truncated = False
    if segment.get("tailLines") and len(lines) > segment["tailLines"]:
        lines = lines[: segment["tailLines"]] + [f"... ({len(lines) - segment['tailLines']} more lines)"]
        truncated = True
    replay = min(MAX_SECONDS, max(MIN_SECONDS, wall * 4))
    captured.append(
        {
            **segment,
            "exitCode": result.returncode,
            "wallSeconds": round(wall, 3),
            "replaySeconds": replay,
            "lines": lines,
            "truncated": truncated,
        }
    )

TYPE_SECONDS = 1.2
PAUSE_SECONDS = 2.6
player = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body { margin: 0; background: #0f1623; }
#term { width: 960px; height: 564px; box-sizing: border-box; padding: 18px 22px; background: #0f1623; color: #d7dde7; font: 13px/1.36 ui-monospace, Menlo, Consolas, monospace; overflow: hidden; white-space: pre; }
.title { color: #9fc1ff; font-weight: 600; }
.prompt { color: #4ad17d; }
.cmd { color: #ffffff; }
.cmdline { white-space: pre-wrap; overflow-wrap: anywhere; }
.out { color: #d7dde7; }
.exit { color: #f4b942; }
#cursor { display: inline-block; width: 9px; height: 17px; background: #d7dde7; vertical-align: -3px; animation: blink 1s steps(1) infinite; }
@keyframes blink { 50% { opacity: 0; } }
</style></head><body><div id="term"><div id="wrap"></div></div>
<script>
const segments = SEGMENTS_JSON;
const TYPE = TYPE_SECONDS, PAUSE = PAUSE_SECONDS;
const term = document.getElementById("term");
const wrap = document.getElementById("wrap");
const sleep = (s) => new Promise((r) => setTimeout(r, s * 1000));
function add(cls, text) { const d = document.createElement("div"); d.className = cls; d.textContent = text; wrap.appendChild(d); term.scrollTop = term.scrollHeight; return d; }
async function play() {
  await sleep(0.8);
  for (const seg of segments) {
    wrap.innerHTML = "";
    add("title", "# " + seg.title);
    add("", "");
    const line = add("cmdline", "");
    const prompt = document.createElement("span"); prompt.className = "prompt"; prompt.textContent = "$ "; line.appendChild(prompt);
    const cmd = document.createElement("span"); cmd.className = "cmd"; line.appendChild(cmd);
    const cursor = document.createElement("span"); cursor.id = "cursor"; line.appendChild(cursor);
    for (let i = 1; i <= seg.command.length; i += 1) { cmd.textContent = seg.command.slice(0, i); await sleep(TYPE / seg.command.length); }
    await sleep(0.35);
    cursor.remove();
    const per = seg.replaySeconds / Math.max(1, seg.lines.length);
    for (const l of seg.lines) { add("out", l); await sleep(per); }
    add("exit", "[exit " + seg.exitCode + "]");
    await sleep(PAUSE);
  }
  document.body.setAttribute("data-done", "1");
}
play();
</script></body></html>"""
player = (
    player.replace(
        "SEGMENTS_JSON",
        json.dumps(
            [
                {
                    "title": c["title"],
                    "command": c["command"],
                    "lines": c["lines"],
                    "exitCode": c["exitCode"],
                    "replaySeconds": c["replaySeconds"],
                }
                for c in captured
            ]
        ),
    )
    .replace("TYPE_SECONDS", str(TYPE_SECONDS))
    .replace("PAUSE_SECONDS", str(PAUSE_SECONDS))
)
player_path = OUT / "demo-player.html"
player_path.write_text(player, encoding="utf-8")

total = sum(TYPE_SECONDS + 0.35 + c["replaySeconds"] + PAUSE_SECONDS for c in captured) + 0.8 + 1
video_dir = OUT / "video-tmp"
shutil.rmtree(video_dir, ignore_errors=True)
with playwright()() as p:
    browser = p.chromium.launch()
    context = browser.new_context(
        viewport={"width": 960, "height": 564}, record_video_dir=str(video_dir), record_video_size={"width": 960, "height": 564}
    )
    page = context.new_page()
    page.goto(f"file://{player_path}")
    page.wait_for_selector("body[data-done='1']", timeout=(total + 30) * 1000)
    page.wait_for_timeout(800)
    context.close()
    browser.close()
webm = next(video_dir.glob("*.webm"))
webm_path = OUT / "demo.webm"
shutil.move(str(webm), webm_path)
shutil.rmtree(video_dir, ignore_errors=True)

mp4 = OUT / "demo.mp4"
gif = OUT / "demo.gif"
palette = OUT / "palette.png"
ff = ["ffmpeg", "-y", "-loglevel", "error"]
subprocess.run(
    [
        *ff,
        "-i",
        str(webm_path),
        "-vf",
        "scale=960:-2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        "26",
        "-movflags",
        "+faststart",
        str(mp4),
    ],
    check=True,
)
subprocess.run(
    [*ff, "-i", str(webm_path), "-vf", "fps=6,scale=800:-1:flags=lanczos,palettegen=max_colors=32", str(palette)], check=True
)
subprocess.run(
    [
        *ff,
        "-i",
        str(webm_path),
        "-i",
        str(palette),
        "-lavfi",
        "fps=6,scale=800:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5",
        str(gif),
    ],
    check=True,
)
palette.unlink()
webm_path.unlink()

manifest = {
    "generatedBy": "tools/record_demo.py",
    "note": "A replay of captured stdout paced by measured wall time, clamped between MIN and MAX seconds per segment; the wall times are pacing data, not benchmarks.",
    "pacing": {
        "minSeconds": MIN_SECONDS,
        "maxSeconds": MAX_SECONDS,
        "multiplier": 4,
        "typeSeconds": TYPE_SECONDS,
        "pauseSeconds": PAUSE_SECONDS,
    },
    "gif": {"fps": 6, "width": 800, "colours": 32, "bytes": gif.stat().st_size},
    "mp4": {"bytes": mp4.stat().st_size},
    "segments": [
        {
            "title": c["title"],
            "command": c["command"],
            "exitCode": c["exitCode"],
            "wallSeconds": c["wallSeconds"],
            "replaySeconds": c["replaySeconds"],
            "lines": len(c["lines"]),
            "truncated": c["truncated"],
        }
        for c in captured
    ],
}
(OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(
    f"record_demo: {len(captured)} segments, GIF {manifest['gif']['bytes'] / 1e6:.2f} MB, MP4 {manifest['mp4']['bytes'] / 1e6:.2f} MB"
)
