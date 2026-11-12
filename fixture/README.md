# The fixture

Written by `fixture/generate.py` from one seed (regeneration is byte-identical under two hash seeds, asserted by a test), around an authored SFDX project. Every figure here is checked by `tools/check_numbers.py`.

## Authored (read by the generator, never written)

- `force-app/main/default/genAiPromptTemplates/Case_Summary.genAiPromptTemplate-meta.xml`: one field-generation template on `Case.Case_Summary__c` with 3 template versions. v1 is Published and active, with terse instructions over nine `{!$Input:Case.<Field>}` merge fields and the `{!$RelatedList:Case.CaseComments.Records}` related list. v2 is a Draft with the same merge fields and instructions rewritten for fluency. v3 is a Draft that adds `{!$Apex:CaseSummaryGrounding.Prompt}` (declared as a `templateDataProviders` entry over `apex://CaseSummaryGrounding`) and `{!$EinsteinSearch:Case_Knowledge_Retriever.Results}`.
- `force-app/main/default/classes/CaseSummaryGrounding.cls`: the Apex data provider, an `@InvocableMethod` with `CapabilityType='PromptTemplateType://einstein_gpt__fieldCompletion'` returning the comment count and the newest comment date as `Prompt`, with its test class. `PromptGateProbe.cls` calls `ConnectApi.EinsteinLLM.generateMessagesForPromptTemplate` and writes the generations shape; both are uncompiled in this repository (no org in this build).
- `force-app/main/default/objects/Case/fields/`: `Case_Summary__c` (long text), `Product__c` (a restricted picklist of six products), `Amount__c` (currency).
- `policy/gate-policy.json` (alpha, power, the reviewed set, the merge-field families, the renderings, the seeds), `policy/claim-grammar.json` (the atom rules) and `policy/fault-model.json` (the stand-in's rates and the reviewer model), each line with a reason.

## Generated

- `data/Case.csv`: 200 cases in the fixture over six products, each with a subject, a description naming the customer and the date the fault started, a priority, a status, a type, an origin, a product, a customer name (`Contact.Name` as `sf data query` writes a relationship field), an amount and the opened date. `data/CaseComment.csv`: 597 case comments, two to four per case: the agent's confirmation with a serial number, then an offer (`Offered a refund of $240.00.`), a callback or an escalation with its date, often an order number with a second request, sometimes a closing note. `data/chunks.jsonl`: 600 retrieved chunks, three per case: two from the case's own product's article and one general, except that in a quarter of cases one of the three is a chunk about another product.
- `generations/v1`, `generations/v2`, `generations/v3`: 600 generated summaries in the Connect REST response shape, with `prompt` equal to the version's content resolved over the case (a test refuses drift). Written by the stand-in model (`src/prg/adapters/fixture.py`) from the case's own values and then faulted at the version's declared rates.
- `reviews/order.txt` (the committed review order; the canonical set of 30 cases is its first thirty) and `reviews/reviewer_a.csv`, `reviewer_b.csv`, `reviewer_c.csv`: 1800 review rows, every reviewer on every case and every version, with a score from one to five, a flag and a note.
- `EXPECTED_VERDICTS.json`: every fault the stand-in applied (kind, atom, displaced value, sentence), the counts per version, the canonical thirty, and the gate verdict for every ordered pair at the thirty and at the full review, derived with the `statistics` module and published t table values rather than with the gate's own distribution code.

## What is planted, and the counts

| Fault class | How the stand-in plants it | What the grammar grades it | Planted |
| --- | --- | --- | --- |
| unsupported | an invented sentence with an RMA, invoice or firmware date the case never had, or the fault's start date shifted to a date in no source | unsupported | 144 planted unsupported |
| contradicted | the priority, the status, the customer or the offered amount displaced by another value the export knows | contradicted | 45 planted contradicted |
| mis-grounded | on v3, the retrieved chunk about another product quoted as the knowledge base's note | misgrounded | 38 planted misgrounded |
| unverifiable | a sentence about how the customer feels | unverifiable, never bad | 238 unverifiable claims |
| omission | an offer or an order sentence dropped | not a claim fault; the reviewer model penalises it | (not gated) |

227 planted faults, 227 of 227 faults recovered, 0 false positives, 0 false negatives, floor 1 in 227.

The rates, from `policy/fault-model.json`: v1 omits a detail often and invents little, so it has 59 bad claims in v1; v2 reads better, omits less and invents more, so 101 bad claims in v2; v3 invents least from nothing and quotes the chunk half the time, so 67 bad claims in v3, of which 38 mis-grounded through a chunk.

## The awkward cases, on purpose

- An invented date is always one the case never had: the first truth let a shifted date land on the opened date, and the planted fault came back supported.
- A displaced customer is always someone the export knows: a person the org has never heard of is not an atom the grammar can see, and the first truth planted contradictions the grounder could not grade.
- A chunk with no product (support hours, refund timing, return labels) applies to every case and is never mis-grounded.
- The Apex provider's text ends with "Newest comment: <date>", which once supported a displaced status of New through a substring test.
- A status word can appear as a verb in a comment ("Escalated to tier 2"), which supports the status atom legitimately; the fixture's seed happens to plant no such collision, and the grammar's reason line says it would be graded supported if it did.

## The reviewer model

Three reviewers score fluency and completeness with independent noise of the same size, one of them harsher by a constant; a bad claim is flagged with a probability well below one and a clean summary is flagged by mistake rarely; a flag costs a point. The model is what makes the fixture's headline possible: 0.860 points between reviewers on one summary, against version effects of a few tenths, so a thirty cannot separate the versions and two hundred can. It is a declared fiction (ADR-005), and the review sheet a real team would fill has the same columns.
