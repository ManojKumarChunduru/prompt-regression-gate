"""The stand-in model: writes a summary from the case's own values, then applies a declared fault model.

It is not a language model and the README says so on its first screen. It reads the same sources
the resolved prompt contains (the merged fields, the comments, the retrieved chunks when the
version merges them), writes three to six sentences from them, and then, at the rates the fault
model declares for the version, omits a detail, invents a sentence with an identifier the case
never had, displaces one atom with a wrong value, quotes the retrieved chunk, or adds a sentence
with nothing checkable in it. Every fault it applies is returned beside the text, which is how the
fixture's planted truth is written (fixture/EXPECTED_VERDICTS.json). Seeded; lists only.
"""

from __future__ import annotations

import datetime as dt
import random
import re
from dataclasses import dataclass, field

from ..exports import Case
from ..metadata import TemplateVersion

NAME = "fixture"

OFFER = re.compile(r"Offered a (\w+) of (\$[\d,]+\.\d{2})")
CALLBACK = re.compile(r"callback on (\d{4}-\d{2}-\d{2})")
ESCALATED = re.compile(r"Escalated to tier 2 on (\d{4}-\d{2}-\d{2})")
ORDER = re.compile(r"order (ORD-\d+) and asked for a (\w+)")
SINCE = re.compile(r"since (\d{4}-\d{2}-\d{2})")


@dataclass
class Fault:
    kind: str  # unsupported, contradicted, misgrounded, unverifiable, omission
    atom_kind: str
    atom: str
    displaced: str
    sentence: str


@dataclass
class Draft:
    sentences: list[str] = field(default_factory=list)
    faults: list[Fault] = field(default_factory=list)


def _shift(date: str, days: int) -> str:
    return (dt.date.fromisoformat(date) + dt.timedelta(days=days)).isoformat()


def _absent_date(case: Case, date: str, days: int) -> str:
    """A date shifted from `date` that appears in no field, comment or chunk of the case: the fault
    model says the invented date is one the case never had, and the first truth let a shifted date
    land on the opened date, which made the planted fault supported."""
    haystack = " ".join(
        list(case.fields.values()) + [c.body + " " + c.created for c in case.comments] + [c.text for c in case.chunks]
    )
    candidate = _shift(date, days)
    while candidate in haystack:
        candidate = _shift(candidate, 1)
    return candidate


def compose(case: Case, version: TemplateVersion, rng: random.Random, model: dict, contacts: list[str]) -> Draft:
    f = case.fields
    product = f.get("Product__c", "")
    contact = f.get("Contact.Name", "")
    subject = f.get("Subject", "")
    symptom = subject[len(product) :].strip() if subject.startswith(product) else subject
    since = SINCE.search(f.get("Description", ""))
    since_date = since.group(1) if since else f.get("CreatedDate", "")
    fluent = model["fluency"] > 0.0
    draft = Draft()

    # 1. The report sentence: contact, product, date.
    if fluent:
        draft.sentences.append(f"{contact} contacted support because the {product} {symptom} since {since_date}.")
    else:
        draft.sentences.append(f"{contact} reported that the {product} {symptom} since {since_date}.")
    # 2. The state sentence: priority and status.
    priority, status = f.get("Priority", ""), f.get("Status", "")
    if fluent:
        draft.sentences.append(f"It is a {priority} priority case and the status is currently {status}.")
    else:
        draft.sentences.append(f"The case is {priority} priority and the status is {status}.")
    # 3. What the agent did, from the comments.
    action_sentence = order_sentence = None
    for comment in case.comments:
        m = OFFER.search(comment.body)
        if m and action_sentence is None:
            action_sentence = f"The agent offered a {m.group(1)} of {m.group(2)}."
        m = CALLBACK.search(comment.body)
        if m and action_sentence is None:
            action_sentence = f"A callback is scheduled for {m.group(1)}."
        m = ESCALATED.search(comment.body)
        if m and action_sentence is None:
            action_sentence = f"The case was escalated to tier 2 on {m.group(1)}."
        m = ORDER.search(comment.body)
        if m and order_sentence is None:
            order_sentence = f"The customer confirmed order {m.group(1)} and asked for a {m.group(2)}."
    details = [s for s in (action_sentence, order_sentence) if s]
    if details and rng.random() < model["omit_detail"]:
        dropped = details.pop(rng.randrange(len(details)))
        draft.faults.append(Fault("omission", "sentence", dropped, "", dropped))
    draft.sentences.extend(details)
    # 4. The retrieved chunk, when the version merges the retriever.
    if version.has("EinsteinSearch") and case.chunks and model["quote_chunk"] > 0.0:
        off = [c for c in case.chunks if c.product and c.product != product]
        chosen = case.chunks[0]
        if off and rng.random() < model["quote_chunk"]:
            chosen = off[0]
        sentence = f"The knowledge base notes that {chosen.text}"
        draft.sentences.append(sentence)
        if chosen.product and chosen.product != product:
            draft.faults.append(Fault("misgrounded", "product", chosen.product, product, sentence))
    # 5. A displaced atom.
    if rng.random() < model["contradict_atom"]:
        kinds = ["priority", "status", "contact", "date"] + (
            ["amount"] if action_sentence and "offered" in action_sentence else []
        )
        kind = rng.choice(kinds)
        if kind == "priority":
            wrong = rng.choice([p for p in ("Low", "Medium", "High") if p != priority])
            index = 1
            draft.sentences[index] = draft.sentences[index].replace(f"{priority} priority", f"{wrong} priority")
            draft.faults.append(Fault("contradicted", "priority", wrong, priority, draft.sentences[index]))
        elif kind == "status":
            wrong = rng.choice([s for s in ("New", "Working", "Escalated", "Closed") if s != status])
            index = 1
            draft.sentences[index] = (
                draft.sentences[index]
                .replace(f"status is currently {status}", f"status is currently {wrong}")
                .replace(f"status is {status}", f"status is {wrong}")
            )
            draft.faults.append(Fault("contradicted", "status", wrong, status, draft.sentences[index]))
        elif kind == "contact":
            wrong = rng.choice([c for c in contacts if c != contact])
            draft.sentences[0] = draft.sentences[0].replace(contact, wrong, 1)
            draft.faults.append(Fault("contradicted", "contact", wrong, contact, draft.sentences[0]))
        elif kind == "date":
            wrong = _absent_date(case, since_date, rng.choice([-7, -3, 2, 5, 11]))
            draft.sentences[0] = draft.sentences[0].replace(since_date, wrong, 1)
            draft.faults.append(Fault("unsupported", "date", wrong, since_date, draft.sentences[0]))
        else:
            m = OFFER.search(action_sentence or "") or re.search(r"(\$[\d,]+\.\d{2})", action_sentence or "")
            amount = re.search(r"\$[\d,]+\.\d{2}", action_sentence or "").group(0)
            value = float(amount.replace("$", "").replace(",", ""))
            wrong = f"${value * rng.choice([0.5, 2.0, 1.5]) + 10:,.2f}"
            index = draft.sentences.index(action_sentence)
            draft.sentences[index] = action_sentence.replace(amount, wrong)
            draft.faults.append(Fault("contradicted", "money", wrong, amount, draft.sentences[index]))
    # 6. An invented sentence, inserted after any displacement so a displacement lands on the sentence it names
    # (the first truth had it the other way round and planted a contradiction on an invented sentence).
    if rng.random() < model["invent_sentence"]:
        template = rng.choice(model["invented_templates"])
        sentence = template.format(
            rma=rng.randint(10000, 99999), inv=rng.randint(10000, 99999), date=_absent_date(case, since_date, rng.randint(3, 40))
        )
        position = rng.randint(1, len(draft.sentences))
        draft.sentences.insert(position, sentence)
        ident = re.search(r"(RMA|INV)-\d+", sentence)
        draft.faults.append(
            Fault("unsupported", "identifier" if ident else "date", ident.group(0) if ident else sentence, "", sentence)
        )
    # 7. Sentiment, with nothing checkable.
    if rng.random() < model["add_sentiment"]:
        sentence = rng.choice(
            [
                "The customer sounds frustrated and wants a quick resolution.",
                "The tone of the thread is polite but increasingly impatient.",
                "The customer seems satisfied with the proposed next step.",
            ]
        )
        draft.sentences.append(sentence)
        draft.faults.append(Fault("unverifiable", "sentence", sentence, "", sentence))
    return draft


def generate(
    case: Case, version: TemplateVersion, rng: random.Random, model: dict, contacts: list[str]
) -> tuple[str, list[Fault]]:
    draft = compose(case, version, rng, model, contacts)
    return " ".join(draft.sentences), draft.faults
