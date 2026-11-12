"""Shared plumbing for the experiments: the fixture paths, one context, one JSON writer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from prg.gate import load_context  # noqa: E402

FIXTURE = ROOT / "fixture"
OUT = ROOT / "docs" / "experiments"
PAIRS = [("v1", "v2"), ("v1", "v3"), ("v2", "v3")]
SETS = ("first30", "all")


def context():
    return load_context(
        FIXTURE,
        FIXTURE / "data",
        FIXTURE / "generations",
        FIXTURE / "reviews",
        FIXTURE / "policy" / "gate-policy.json",
        FIXTURE / "policy" / "claim-grammar.json",
    )


def truth() -> dict:
    return json.loads((FIXTURE / "EXPECTED_VERDICTS.json").read_text(encoding="utf-8"))


def write(name: str, payload: dict) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def pct(part: float, whole: float) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def table(rows: list[list], headers: list[str]) -> str:
    widths = [max(len(str(h)), *(len(str(r[i])) for r in rows)) if rows else len(str(h)) for i, h in enumerate(headers)]
    out = ["  ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers)), "  ".join("-" * w for w in widths)]
    out += ["  ".join(str(c).ljust(widths[i]) for i, c in enumerate(r)) for r in rows]
    return "\n".join(out)
