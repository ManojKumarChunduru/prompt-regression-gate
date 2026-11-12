# ADR-002: Claim-level grounding against the resolved prompt's own contract

Status: accepted, 2026-11-12.

## Context

A review score cannot see a claim the case does not support, because the reviewer reads the summary and not the resolved prompt; on the fixture, v2 summaries with a contradicted claim score 3.348 and clean v2 summaries score 3.342. The gate needs a second dimension that reads what the model read.

## Decision

Every summary is split into claims (sentences) and every claim into atoms by a declared grammar with a reason per rule: dollar figures, ISO dates, durations with a unit, serial and order identifiers, priority and status picklist values, product names and customer names drawn from the export's own values, and action words. Each atom is matched against the grounding contract of the version that wrote the summary: the fields named by its `{!$Input:Case.<Field>}` merge fields, the comments its related list renders (with their dates), the text its Apex or Flow data provider returns, and the chunks its retriever brought in. The contract is read from the committed `GenAiPromptTemplate` metadata, and a generation whose committed `prompt` differs from the template resolved over the export is refused, so the contract and the model's input cannot drift apart.

Five verdicts, a claim taking the worst of its atoms: supported, contradicted (the atom plays a role with a field counterpart in the contract, the field holds a different value, no comment says the atom), unsupported (nothing in the resolved prompt contains it), mis-grounded (only a retrieved chunk contains it and the chunk is about another product; a chunk with no product applies to every case), unverifiable (no atom). Bad means unsupported, contradicted or mis-grounded. Vocabulary rules run before pattern rules, so a product name the export knows wins any overlap; containment is whole-word.

The contract is strict on purpose: a claim that is true of the org but comes from a field the template did not merge in is unsupported, because the model could not have read it.

## Alternatives rejected

- **An LLM judge.** Higher recall on real summaries, and a model at gate time: non-deterministic, keyed, and a second model whose own regressions the gate cannot see. It is the Pivot, with its trigger: a withheld, hand-labelled set on which the grammar's recall has been measured and found short.
- **Overlap against a reference summary** (ROUGE and relatives). A sentence with a wrong amount scores as well as the right one when the words match; the grammar grades it contradicted.
- **Grounding against the whole export.** Would call a claim supported when the model could not have read the field; the contract is what the model saw.

## The grammar's blind spots, published

- A customer or a product the export does not know is not an atom; the fixture plants displaced customers only from names the export knows, and says so.
- A status word that a comment uses as a verb ("Escalated to tier 2") supports the status atom legitimately.
- A date can belong to many roles, so an unseen date is unsupported and never contradicted.
- A sentence with no atom is unverifiable: 238 unverifiable claims on the fixture, 8.8% of claims unverifiable, counted and never gated on.

Recall is measured against the planted faults: 227 of 227 faults recovered, 0 false positives, 0 false negatives, floor 1 in 227 on the author's own planting. Three grammar bugs were found by that measurement and are pinned in `tests/test_bugs.py`: whole-word containment ("Newest comment" supported the status New), vocabulary rules before patterns ("2 units" ate "Aero 2"), and the comment's date as part of the comment source.

## Consequences

The grounding dimension runs on every generated case (two hundred), not only the reviewed thirty, so its floor is lower than the reviews' and it decides pairs the reviews cannot: the fluent rewrite carries 0.210 more bad claims per case than v1 and is blocked at thirty and at two hundred.
