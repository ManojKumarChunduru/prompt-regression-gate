# ADR-005: What a committed fixture cannot establish

Status: accepted, 2026-11-12.

## Context

The fixture is an authored SFDX project with generated exports, generations and reviews, and a planted truth derived from the generator's own intent. Every figure in the README is reproducible from it offline. That is the right default (receipts beat realism), and it is also a boundary: 227 of 227 faults recovered checks the grammar on a fixture built to be recovered, with a floor of 1 in 227, and the floor at thirty is the declared reviewer model's spread.

## Declared inputs, each with the experiment that would settle it

1. **The summaries are a stand-in's, not a model's.** The bad-claim rates (59 bad claims in v1, 101 bad claims in v2, 67 bad claims in v3) are the fault model's rates applied by a seeded generator; they say nothing about any model. Experiment: `PromptGateProbe.run('Case_Summary', ids, false)` in a Developer Edition org with the fixture's cases loaded, for each of the three versions, written to `generations/`, and `prg gate` run unchanged.
2. **The reviews are a declared noise model's.** 0.860 points between reviewers on one summary and 41.1% pairwise reviewer agreement are properties of `fixture/policy/fault-model.json`, chosen so that thirty cannot separate the versions and two hundred can. Experiment: three people score the canonical thirty with the fixture's review sheet; the floor becomes theirs.
3. **The merge-field syntax inside `content` is partly declared.** The Metadata API sample documents `{!$Input:<Reference>.<Field>}` and `{!$Flow:<Provider>.<Output>}`; the related-list form appears in two spellings in Trailhead and community material, and the Apex and retriever forms are by analogy. The parser accepts the five families the policy names and refuses any other; the resolved prompt the fixture commits renders the related list and the retriever by declared templates (`related_list_rendering`, `retriever_rendering` in the policy, each with a reason). Experiment: the probe with `isPreview` true returns the resolved prompt the platform builds, which settles both the syntax and the rendering.
4. **The grammar's recall is measured on the author's planting.** 0 false negatives and 0 false positives are each a rate below 1 in 227. A name or a product the export does not know is invisible; a status word used as a verb in a comment supports the status atom. Experiment: hand-label the probe's summaries and measure recall against those labels; that number is the Pivot's trigger.
5. **The live adapters produce no number.** `prg generate --adapter openai` and `--adapter gemini` write the same file shape from a key in the environment and are never run in CI; a subprocess test asserts 0 forbidden modules on the default path. Experiment: run them, commit nothing, and compare the gate's verdict on their output with the probe's.
6. **The minimum n is a central-t approximation.** The noncentral t gives the exact power; the fixed-point iteration on central quantiles is the textbook approximation. Its error here is published: the careful formula says 123 reviews and the careful rewrite clears at 70 reviews along the committed order, the fluent formula says 30 reviews and the fluent rewrite clears at 23 reviews. The committed order is one prefix sequence; the 500 draws of thirty are the distribution.
7. **The Apex provider is uncompiled.** `CaseSummaryGrounding.cls` follows the documented `@InvocableMethod(CapabilityType=...)` shape with a `Request` carrying the case and a `Response` carrying `Prompt`; the offline gate renders the same two facts for the resolved prompt. Experiment: deploy it, add it to v3 in Prompt Builder, and compare the preview's resolved prompt with the committed one.
8. **Template activations, batch processing and the Trust Layer are out of scope.** `GenAiPromptTemplateActv`, Prompt Template Batch Processing, and the response's `slotsMaskingInformation`, `contentQualityRepresentation` and `safetyScoreRepresentation` fields are read and ignored.

## What the fixture does support

Everything in the claims tables: the paired tests, the floor, the minimum n, the sign test and the bootstrap, the draws, the five verdicts and the contract, the refusals and the decision rule, the matrix. Those are properties of the code, and the planted truth exercises every fault class and every row.

## What it would take to claim discovery

The probe run for the three versions in an org, a review sheet filled by three people for the thirty, and the grammar's recall measured on those summaries against hand labels. Until then the numbers to quote are the floor with its n and the recall with its floor, and the first metric to watch is the share of bad claims the real reviewers flag.
