# ADR-003: Standard library statistics, implemented and tested; a stand-in model with a declared fault model

Status: accepted, 2026-11-12.

## Context

The gate is a PR check. It runs on a runner that has Python and the package, and it has to produce the same numbers on three interpreters and from a fresh clone with no network. It also needs a corpus of generated summaries and reviews that a reviewer can regenerate byte for byte.

## Decision

1. **The statistics are in `src/prg/stats.py`, standard library only.** Student's t through the regularised incomplete beta (a continued fraction and `math.lgamma`), the quantile by bisection on the CDF (cached), the paired t and its interval, the floor, the minimum n by bracketing and bisection, the exact sign test (`math.comb`), Cohen's kappa, Spearman's rank correlation with averaged ties, and a percentile bootstrap over a seeded `random.Random` on a list. The t CDF and quantile are tested against eleven published critical values; the floor against the hand formula; the minimum n against a linear walk.
2. **Generations are committed in the Connect REST response shape** (`generations[].text`, `prompt`, `promptTemplateDevName`, `requestId`), one file per case per version, so the probe class, the live adapters and the stand-in write one shape and the gate reads one shape.
3. **The corpus comes from a stand-in model with a declared fault model.** The stand-in writes each summary from the case's own values (the report sentence, the state sentence, the offer or callback or escalation, the order, the retrieved chunk on v3) and applies the version's rates from `fixture/policy/fault-model.json`: omit a detail, invent a sentence with an identifier the case never had, displace one atom, quote the chunk, add a sentence with nothing checkable. Every fault it applies is recorded beside the text, which is how the planted truth is written. The reviews come from a declared reviewer model in the same file.
4. **The live adapters are extras, imported inside their functions.** `prg generate --adapter openai|gemini` writes the same shape with a key from the environment; no number in this repository comes from them, and a subprocess test asserts a gate run leaves 0 forbidden modules on the default path.

## Alternatives rejected

- **scipy or statsmodels.** Correct and large; a gate that needs scipy on the runner is a gate that does not run on the runner, and the three functions the gate needs are a few dozen lines each with table values to test against.
- **Real model outputs committed as the fixture.** Not reproducible: the same prompt returns different text on different days, and the planted truth could not be written. Reproducibility is worth more than realism here; ADR-005 names the experiment that puts a real model behind the same files.
- **Hand-written summaries.** Two hundred times three, with faults the author would plant by hand; the stand-in plants at declared rates and records what it did, which is the only way the recall number means anything.

## Consequences

`make verify` passes from a fresh clone with the network proxy pointed at a dead port, and the experiment JSON is byte-identical across Python 3.11, 3.12 and 3.13. The bad-claim rates (59 bad claims in v1, 101 bad claims in v2, 67 bad claims in v3) are properties of the fault model and are presented as such on the README's first screen. The first `minimum_n` walked n upwards and took minutes on a floor in the thousands; it brackets and bisects now, pinned by a test.
