# ADR-004: A demonstrated regression wins over an undecided dimension, and the service cannot disagree with the CLI

Status: accepted, 2026-11-12.

## Context

The gate has two dimensions and four exit codes, and the two dimensions can disagree: on the fixture there are 3 rows where a regression wins, where the reviews are undecided and the grounding is demonstrably worse. The previous repository (the sharing audit) ordered its codes the other way, with "undecidable" winning over "hidden exposure". The gate also has a second surface, a FastAPI service, which must not become a second implementation.

## Decision

1. **Exit codes.** 0 ship: the reviews are better and the grounding is not demonstrably worse. 1 blocked: either dimension is worse. 2 cannot decide: the reviews are undecided or refused, or the grounding is refused, and nothing is worse. 3 usage. **1 wins over 2.** The sharing audit asked "is anything hidden?", where an undecided pair means the answer is unknown and a pipeline must not act on a partial list; this gate asks "may this ship?", where a demonstrated regression answers the question whatever else is unknown. "Cannot assert ship" is the verdict only when nothing has been demonstrated. Both orders are right for their question, and the exit-code module says so in its docstring.
2. **Ship needs the reviews.** A candidate whose grounding is better but whose reviews are undecided exits 2 (v2 to v3 on the fixture, at thirty and at two hundred): fewer bad claims is necessary, a score the sample can see is also necessary, and the reason line says which is missing and how many reviews it would take.
3. **A refused grounding is a cannot-decide on its own.** A version whose template merges a field the export lacks (`{!$Input:Case.Rating}` with no `Rating` column) has its grounding refused with the field named, and the pair exits 2 unless the reviews are worse.
4. **The service is the same functions behind four routes.** `prg serve` builds a FastAPI app whose routes call `run_gate`, `power_payload`, `grounding_census` and the grounded summaries and nothing else; a test asserts the gate over HTTP and the gate in process return the same exit code, p and effect. FastAPI is imported inside `create_app`, so the module costs nothing on the default path and a missing extra is a usage error with the install command in it.
5. **n cannot shrink silently.** The review reader refuses a reviewer who scored fewer cases than the set, a score outside the policy's range, a case not in the committed order, and a duplicate row, each with the file and row named, because a dropped row lowers n without lowering the verdict's confidence in anyone's eyes.

## Alternatives rejected

- **2 wins over 1, as in the sharing audit.** Would let a fluent rewrite with more fabrications exit "cannot decide" because its reviews were inconclusive; a pipeline reading 2 as "needs more reviews" would collect more reviews and then ship it. The regression is known now.
- **`--strict` to turn 2 into 1.** The sharing audit left it out because a refusal is not a tie; the gate leaves it out because the number of reviews is not a knob a flag should turn.
- **A service with its own scoring.** The point of the service is that a pipeline and a laptop get the same number; a second implementation would be a second source of disagreement.

## Consequences

The CI gate job installs the package alone and runs three rows of the matrix, expecting exit 2, 0 and 1 in turn, so every verdict code is proven by the repository's own workflow (12 gate rows, 1 row exits 0, 7 rows exit 1, 4 rows exit 2). The rollback rows (v2 to v1) exit 1 on the reviews and better on grounding, which is the honest verdict on a rollback.
