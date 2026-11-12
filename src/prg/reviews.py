"""Reads the hand reviews and pairs them per case.

One CSV per reviewer (caseId, version, score, flagged, note), an `order.txt` that fixes the order
cases were reviewed in (the first thirty are the canonical sample), and nothing else. A reviewer
who scored fewer cases than the set, or a score outside the policy's range, is refused with the
file and row named: a missing row would silently shrink n, which is the one thing the gate must
not let happen.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from .exit_codes import PrgError
from .policy import Policy


@dataclass
class Review:
    reviewer: str
    case_id: str
    version: str
    score: int
    flagged: bool
    note: str


@dataclass
class Reviews:
    reviewers: list[str]
    order: list[str]
    rows: list[Review]
    by_key: dict[tuple[str, str, str], Review]  # (reviewer, case, version)

    def versions(self) -> list[str]:
        seen: list[str] = []
        for r in self.rows:
            if r.version not in seen:
                seen.append(r.version)
        return seen

    def reviewed_set(self, which: str) -> list[str]:
        if which == "all":
            return list(self.order)
        if which == "first30":
            return self.order[:30]
        raise PrgError(f"reviewed set {which!r} is not first30 or all")

    def score(self, reviewer: str, case_id: str, version: str) -> int:
        return self.by_key[(reviewer, case_id, version)].score

    def case_mean(self, case_id: str, version: str) -> float:
        return mean(self.score(r, case_id, version) for r in self.reviewers)

    def flagged_by_any(self, case_id: str, version: str) -> bool:
        return any(self.by_key[(r, case_id, version)].flagged for r in self.reviewers)

    def paired_differences(self, baseline: str, candidate: str, case_ids: list[str]) -> list[float]:
        """Candidate minus baseline, per case, on the mean of the reviewers."""
        return [self.case_mean(c, candidate) - self.case_mean(c, baseline) for c in case_ids]

    def preferences(self, reviewer: str, baseline: str, candidate: str, case_ids: list[str]) -> list[str]:
        out = []
        for c in case_ids:
            d = self.score(reviewer, c, candidate) - self.score(reviewer, c, baseline)
            out.append("candidate" if d > 0 else "baseline" if d < 0 else "tie")
        return out


def read_reviews(reviews_dir: Path, policy: Policy, versions: list[str] | None = None) -> Reviews:
    reviews_dir = Path(reviews_dir)
    order_path = reviews_dir / "order.txt"
    try:
        order = [line.strip() for line in order_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except FileNotFoundError as exc:
        raise PrgError(f"review order not found: {order_path}") from exc
    if len(set(order)) != len(order):
        raise PrgError(f"{order_path}: a case id appears twice")
    files = sorted(reviews_dir.glob("*.csv"))
    if not files:
        raise PrgError(f"{reviews_dir}: no reviewer CSV files")
    rows: list[Review] = []
    by_key: dict[tuple[str, str, str], Review] = {}
    reviewers: list[str] = []
    for path in files:
        reviewer = path.stem
        reviewers.append(reviewer)
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for column in ("caseId", "version", "score", "flagged"):
                if column not in (reader.fieldnames or []):
                    raise PrgError(f"{path}: column {column!r} is missing")
            for index, raw in enumerate(reader, start=2):
                try:
                    score = int(raw["score"])
                except ValueError as exc:
                    raise PrgError(f"{path}: row {index}: score {raw['score']!r} is not an integer") from exc
                if not policy.score_min <= score <= policy.score_max:
                    raise PrgError(f"{path}: row {index}: score {score} is outside {policy.score_min} to {policy.score_max}")
                if raw["caseId"] not in order:
                    raise PrgError(f"{path}: row {index}: case {raw['caseId']} is not in order.txt")
                review = Review(
                    reviewer, raw["caseId"], raw["version"], score, raw["flagged"].strip().lower() == "yes", raw.get("note", "")
                )
                key = (reviewer, review.case_id, review.version)
                if key in by_key:
                    raise PrgError(f"{path}: row {index}: {reviewer} scored {review.case_id} {review.version} twice")
                by_key[key] = review
                rows.append(review)
    seen_versions = []
    for r in rows:
        if r.version not in seen_versions:
            seen_versions.append(r.version)
    expected = versions or seen_versions
    for reviewer in reviewers:
        for case_id in order:
            for version in expected:
                if (reviewer, case_id, version) not in by_key:
                    raise PrgError(
                        f"{reviews_dir / (reviewer + '.csv')}: no score for case {case_id} version {version}; "
                        "n would shrink silently"
                    )
    return Reviews(reviewers=reviewers, order=order, rows=rows, by_key=by_key)
