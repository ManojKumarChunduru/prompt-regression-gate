"""Experiment 5: the gate matrix.

Every ordered version pair at the canonical thirty and at the full review, both dimensions and the
exit code, with the rule that a demonstrated regression wins over an undecided dimension shown on
the rows where it bites; and the default-path import check, which lists the optional modules a
gate run leaves in sys.modules (expected: none).
"""

import ast
import subprocess
import sys
from collections import Counter

from lib import FIXTURE, SETS, context, table, write
from prg.adapters import FORBIDDEN_ON_DEFAULT_PATH
from prg.gate import run_gate


def main() -> None:
    ctx = context()
    rows = []
    for baseline in ctx.versions():
        for candidate in ctx.versions():
            if baseline == candidate:
                continue
            for which in SETS:
                r = run_gate(ctx, baseline, candidate, which)
                rows.append(
                    {
                        "baseline": baseline,
                        "candidate": candidate,
                        "reviewedSet": which,
                        "reviews": r.reviews.direction,
                        "reviewsEffect": round(r.reviews.test.mean_diff, 4),
                        "grounding": r.grounding.direction,
                        "groundingEffect": round(r.grounding.test.mean_diff, 4),
                        "exitCode": r.exit_code,
                        "regressionWinsOverUndecided": r.exit_code == 1
                        and "undecided" in (r.reviews.direction, r.grounding.direction),
                    }
                )
    code = (
        "import sys, prg.cli\n"
        f"prg.cli.main(['gate', '--project', r'{FIXTURE}', '--baseline', 'v1', '--candidate', 'v3', '--quiet'])\n"
        f"print([m for m in {list(FORBIDDEN_ON_DEFAULT_PATH)!r} if m in sys.modules])\n"
    )
    found = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True).stdout.strip()
    counts = Counter(r["exitCode"] for r in rows)
    payload = {
        "rows": rows,
        "exitCounts": {str(k): v for k, v in sorted(counts.items())},
        "regressionWinsRows": sum(1 for r in rows if r["regressionWinsOverUndecided"]),
        "defaultPathForbiddenFound": ast.literal_eval(found),
        "defaultPathForbiddenCount": len(ast.literal_eval(found)),
    }
    write("exp05_gate_matrix", payload)
    print(
        table(
            [
                [
                    r["baseline"],
                    r["candidate"],
                    r["reviewedSet"],
                    r["reviews"],
                    r["reviewsEffect"],
                    r["grounding"],
                    r["groundingEffect"],
                    r["exitCode"],
                ]
                for r in rows
            ],
            ["baseline", "candidate", "set", "reviews", "effect", "grounding", "effect", "exit"],
        )
    )
    print(
        f"exit codes: {dict(counts)}; rows where a regression wins over an undecided dimension: {payload['regressionWinsRows']}; forbidden modules on the default path: {payload['defaultPathForbiddenCount']}"
    )


if __name__ == "__main__":
    main()
