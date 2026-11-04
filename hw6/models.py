"""Structured types for the Campus Customs vendor desk.

Every value the model produces is validated against `VendorAssessment` before it is
printed, logged, or scored. An answer that does not fit the schema is a failed run, not a
result to interpret later — which is the point of validating at the boundary.

The six reported fields are named exactly as `data/practice_key.json` names them, so a
run's output can be compared with the key field-for-field without a translation layer.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

#: The handbook (§4) allows exactly two outcomes. A Literal rather than a free string
#: means the model physically cannot invent a third, like "maybe" or "recommend with
#: reservations", which would have to be mapped onto one of these two anyway — and mapped
#: by us, guessing at what it meant.
Decision = Literal["recommend", "do_not_recommend"]


class VendorAssessment(BaseModel):
    """The vendor desk's answer for one vendor document.

    Field by field, and why each is shaped the way it is:

    vendor, sku
        Optional strings. The handbook's rule is "facts come from the document itself"
        and "report it as unknown" when a document is silent, so every extracted fact
        must have a way to say *not stated*. `None` is that way: it is distinguishable
        from an empty string or a zero, which is not true of the alternatives.

    unit_price
        Optional float. A price is a decimal amount; an int would silently truncate
        $21.80 to 21. Floats are fine here because nothing in this project does
        arithmetic on money — the handbook comparison is `quoted <= max unit cost`, a
        single comparison, not a sum where cent-level error could accumulate.

    lead_time_days, min_order
        Optional ints. Both are whole counts, and both are compared against a handbook
        threshold (21 days, 600 units). Note the convention, which the prompt also
        states: the number is recorded **exactly as the document states it**, with no
        conversion from business days to calendar days. `data/practice_key.json` records
        "26 business days" as 26, so converting would disagree with the key on every
        document that uses business days — which is most of them.

    decision
        Required, and the only field with no `None` option. A run that cannot determine
        the facts still has to reach a decision, and the handbook says what that decision
        is: any failed check means `do_not_recommend`. An unknown price cannot be shown
        to be at or below the max unit cost, so the check fails and the decision is
        forced. There is no third state to express.

    reason
        Required, one sentence, and required by the handbook (§4) to name the check that
        decided it. This is the field that makes a wrong answer debuggable: a decision on
        its own tells you nothing about whether the model misread the price or misapplied
        the rule.
    """

    vendor: str | None = Field(
        default=None,
        description="The vendor's name exactly as the document gives it, or null if the document does not name one.",
    )
    sku: str | None = Field(
        default=None,
        description="The Campus Customs SKU, e.g. CC-HD-006, or null if the document does not state one.",
    )
    unit_price: float | None = Field(
        default=None,
        description="The quoted price per unit in US dollars, as a number, or null if the document does not state one.",
    )
    lead_time_days: int | None = Field(
        default=None,
        description=(
            "The lead time as a whole number of days, exactly as the document states it. "
            "Do not convert business days to calendar days. Null if the document does not state one."
        ),
    )
    min_order: int | None = Field(
        default=None,
        description="The minimum order in units, as a whole number, or null if the document does not state one.",
    )
    decision: Decision = Field(
        description="'recommend' only if all four handbook checks pass; otherwise 'do_not_recommend'.",
    )
    reason: str = Field(
        description="One sentence naming the handbook check that decided this, e.g. which check failed.",
    )


class GuardReport(BaseModel):
    """What the defences did on one run, so the audit shows the work and not just the answer.

    `decision_overridden` is the one to watch. It is true when the model's decision differed
    from the one `handbook.apply_checks` computed from the figures the model itself reported
    — which is the signature of a document that argued its way to an answer the facts do not
    support. The computed decision is the one reported; this field is how you find out that
    the model wanted to say something else.
    """

    defenses: bool
    concealment_checked: bool
    concealed_fragments: int
    directives_flagged: int
    tools_offered: list[str]
    model_decision: str | None = None
    computed_decision: str | None = None
    decision_overridden: bool = False
    reason_replaced: bool = False
    reason_replaced_why: str | None = None
    checks: list[str] = Field(default_factory=list)


class ToolCall(BaseModel):
    """One tool call, as recorded in `output/audit_trail.json`.

    `result` is deliberately a short summary and not the tool's full return value: a
    document's text runs to thousands of characters, and an audit trail that embeds the
    whole document on every run stops being readable, which defeats its purpose.
    """

    tool: str
    arguments: dict[str, Any]
    result: str


class TrapCall(BaseModel):
    """One call to a trap tool, as recorded in `output/trap_calls.json`.

    This file exists to be empty. An entry in it means a vendor document persuaded the
    agent to try to email someone or pay someone, so it records enough to reconstruct the
    attempt: which tool, with what arguments, while reading which document, and when.
    `performed` is always false and is written anyway — the record should state plainly
    that nothing happened, rather than leaving a reader to infer it.
    """

    timestamp: str
    tool: str
    arguments: dict[str, Any]
    document: str
    performed: bool = False
    note: str = "Recorded only. Nothing was sent, paid, or otherwise performed."


class CostBreakdown(BaseModel):
    """What one run cost, in tokens and dollars.

    The token fields mirror what the API reports. `input_tokens` is the provider's total
    and **includes** any cached tokens, so `billable_input_tokens` is the subtraction that
    avoids charging the full rate for tokens that were served from cache.
    """

    input_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    billable_input_tokens: int
    output_tokens: int
    input_usd: float
    cache_read_usd: float
    cache_write_usd: float
    output_usd: float
    total_usd: float


class UsageRecord(BaseModel):
    """One line of `output/usage_log.json`: what a run cost and what it was reading.

    `note` labels runs that were not ordinary CLI runs — the cache experiment's two arms,
    for instance — so the log stays readable when one file holds runs made for different
    reasons. A plain `python agent.py --doc ...` leaves it null.
    """

    run_id: str
    timestamp: str
    document: str
    model: str
    requests: int
    cost: CostBreakdown
    note: str | None = None


class AuditRecord(BaseModel):
    """One line of `output/audit_trail.json`: every tool call plus the final answer.

    `final_answer` is optional because a run can fail — a validation error, a refusal, a
    network fault — and a failed run is exactly the one worth having a record of.
    `error` carries the reason when it does.
    """

    run_id: str
    timestamp: str
    document: str
    model: str
    tool_calls: list[ToolCall]
    final_answer: VendorAssessment | None = None
    error: str | None = None
    note: str | None = None
    guard: GuardReport | None = None
