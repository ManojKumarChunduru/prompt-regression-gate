"""The declared inputs, each with a reason, read from a policy file.

Alpha, power, the reviewed set, the merge-field families the parser accepts, how a related list
is rendered into the resolved prompt, the bootstrap and draw seeds: none of these is a
measurement, so none is hidden in code. `prg policy` prints the file as the gate read it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .exit_codes import PrgError

DEFAULT_POLICY: dict = {
    "alpha": {"value": 0.05, "reason": "two-sided significance level for every paired test; the conventional value, declared"},
    "power": {
        "value": 0.8,
        "reason": "the power at which the minimum n and the noise floor are computed; conventional, declared",
    },
    "reviewed_set": {
        "value": "first30",
        "reason": "the review sample the gate reads by default: the first thirty case ids of reviews/order.txt; `all` reads every review",
    },
    "merge_field_families": {
        "value": ["Input", "RelatedList", "Flow", "Apex", "EinsteinSearch"],
        "reason": "Input and Flow are in the Metadata API sample; RelatedList, Apex and EinsteinSearch are declared (ADR-005)",
    },
    "related_list_rendering": {
        "value": "- [{CreatedDate}] {CommentBody}",
        "reason": "how the resolved prompt renders one related-list record; the platform's rendering is not documented, so this is declared",
    },
    "retriever_rendering": {
        "value": "- ({ChunkId}) {Text}",
        "reason": "how the resolved prompt renders one retrieved chunk; declared for the same reason",
    },
    "bootstrap": {"value": {"reps": 2000, "seed": 11}, "reason": "the readers' second interval; seeded so two runs agree"},
    "draws": {
        "value": {"count": 500, "size": 30, "seed": 23},
        "reason": "experiment 2's thirties drawn from the full review; seeded",
    },
    "score_range": {"value": [1, 5], "reason": "a review score outside this range is refused with the file and row named"},
    "grounding_sources": {
        "value": {"field": "Input", "comment": "RelatedList", "chunk": "EinsteinSearch", "provider": "Apex"},
        "reason": "which merge-field family brings each source kind into the resolved prompt; a claim is supported only by a source the template merged in",
    },
}


@dataclass
class Policy:
    alpha: float
    power: float
    reviewed_set: str
    merge_field_families: list[str]
    related_list_rendering: str
    retriever_rendering: str
    bootstrap_reps: int
    bootstrap_seed: int
    draws_count: int
    draws_size: int
    draws_seed: int
    score_min: int
    score_max: int
    grounding_sources: dict[str, str]
    reasons: dict[str, str] = field(default_factory=dict)
    source: str = "built-in defaults"

    @classmethod
    def from_dict(cls, raw: dict, source: str) -> Policy:
        merged = {k: dict(v) for k, v in DEFAULT_POLICY.items()}
        for key, entry in raw.items():
            if key not in merged:
                raise PrgError(f"{source}: unknown policy key {key!r}")
            if not isinstance(entry, dict) or "value" not in entry or "reason" not in entry:
                raise PrgError(f"{source}: policy key {key!r} needs a value and a reason")
            merged[key] = entry
        v = {k: e["value"] for k, e in merged.items()}
        if not 0 < float(v["alpha"]) < 1 or not 0 < float(v["power"]) < 1:
            raise PrgError(f"{source}: alpha and power must be strictly between 0 and 1")
        if v["reviewed_set"] not in ("first30", "all"):
            raise PrgError(f"{source}: reviewed_set must be first30 or all, not {v['reviewed_set']!r}")
        lo, hi = v["score_range"]
        return cls(
            alpha=float(v["alpha"]),
            power=float(v["power"]),
            reviewed_set=v["reviewed_set"],
            merge_field_families=list(v["merge_field_families"]),
            related_list_rendering=v["related_list_rendering"],
            retriever_rendering=v["retriever_rendering"],
            bootstrap_reps=int(v["bootstrap"]["reps"]),
            bootstrap_seed=int(v["bootstrap"]["seed"]),
            draws_count=int(v["draws"]["count"]),
            draws_size=int(v["draws"]["size"]),
            draws_seed=int(v["draws"]["seed"]),
            score_min=int(lo),
            score_max=int(hi),
            grounding_sources=dict(v["grounding_sources"]),
            reasons={k: e["reason"] for k, e in merged.items()},
            source=source,
        )

    def lines(self) -> list[str]:
        """The policy as the gate read it, one line per input with its reason."""
        values = {
            "alpha": self.alpha,
            "power": self.power,
            "reviewed_set": self.reviewed_set,
            "merge_field_families": ", ".join(self.merge_field_families),
            "related_list_rendering": self.related_list_rendering,
            "retriever_rendering": self.retriever_rendering,
            "bootstrap": f"reps {self.bootstrap_reps}, seed {self.bootstrap_seed}",
            "draws": f"count {self.draws_count}, size {self.draws_size}, seed {self.draws_seed}",
            "score_range": f"{self.score_min} to {self.score_max}",
            "grounding_sources": ", ".join(f"{k} via {v}" for k, v in self.grounding_sources.items()),
        }
        return [f"{key} = {values[key]}  ({self.reasons[key]})" for key in values]


def load_policy(path: Path | None) -> Policy:
    if path is None:
        return Policy.from_dict({}, "built-in defaults")
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PrgError(f"policy file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PrgError(f"{path}: not valid JSON ({exc.msg} at line {exc.lineno})") from exc
    if not isinstance(raw, dict):
        raise PrgError(f"{path}: the policy must be a JSON object")
    return Policy.from_dict(raw, str(path))
