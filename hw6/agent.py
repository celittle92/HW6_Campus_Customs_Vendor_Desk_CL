#!/usr/bin/env python3
"""The Campus Customs vendor desk agent — entry point.

Reads one vendor document and returns a structured recommendation:

    python agent.py --doc data/practice_docs/p01_bluehen_quote.html

Every run appends to three files in `output/`:

    usage_log.json    what the run cost, from the token counts the API reported
    audit_trail.json  every tool call with its arguments and a short result, plus the answer
    trap_calls.json   only ever written to when a document talks the agent out of its job

The agent is PydanticAI over `gpt-6-luna`, routed through Portkey. The model is pinned in
`app_config.REQUIRED_OPENAI_MODEL` and cannot be changed by the environment.

`OpenAIResponsesModel` rather than the default chat-completions model: luna models reject
function tools on `/v1/chat/completions`, and this agent has three.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from app_config import build_portkey_client, load_settings
from handbook import apply_checks, parse_handbook
from models import AuditRecord, GuardReport, UsageRecord, VendorAssessment
from tools import (
    AUDIT_TRAIL_PATH,
    DEFENDED_TOOLS,
    OUTPUT_DIR,
    USAGE_LOG_PATH,
    VENDOR_DESK_TOOLS,
    VendorDeskDeps,
    append_json_list,
    cost_breakdown,
    ensure_trap_file,
    extract_document,
    format_document,
    load_rates,
)

HERE = Path(__file__).resolve().parent
PROMPT_PATH = HERE / "prompts" / "prompt.md"
UNDEFENDED_PROMPT_PATH = HERE / "prompts" / "prompt_problem3.md"
HANDBOOK_PATH = HERE / "data" / "shop_handbook.md"
HANDBOOK_PLACEHOLDER = "{{HANDBOOK}}"

#: Things that have no business in an answer: a link the vendor wanted carried to the buyer,
#: or one of our own cost ceilings, which handbook §4 forbids repeating to anyone.
URL_IN_ANSWER = re.compile(r"https?://\S+|\bwww\.\S+", re.I)


def build_instructions(prompt_path: Path = PROMPT_PATH) -> str:
    """Load the runtime prompt and splice the handbook into it.

    The handbook goes where `prompts/prompt.md` puts the placeholder rather than being
    concatenated here, so the prompt file controls the whole running order — including the
    reminder that comes *after* the handbook, which would be impossible if this function
    just appended one file to the other.

    Order matters for cost as well as for instruction-following. Both halves are identical
    on every run, so the entire instruction block is a stable prefix that a prompt cache can
    serve: at 10,058 handbook tokens that is the difference between $1.01 and $0.10 per
    thousand calls (see `output/handbook_estimate.md`). The per-document text arrives later,
    as a tool result, which is exactly where it has to be for the prefix to stay stable.
    """
    prompt = prompt_path.read_text(encoding="utf-8")
    if HANDBOOK_PLACEHOLDER not in prompt:
        raise SystemExit(
            f"{prompt_path.name} no longer contains {HANDBOOK_PLACEHOLDER}; "
            "the handbook would not be sent to the model."
        )
    return prompt.replace(HANDBOOK_PLACEHOLDER, HANDBOOK_PATH.read_text(encoding="utf-8"))


def build_agent(
    instructions: Any = None,
    model_settings: Any = None,
    *,
    defenses: bool = True,
) -> tuple[Agent[VendorDeskDeps, VendorAssessment], str]:
    """Build the agent. Returns it and the model name actually in use.

    Both arguments exist for `cache_test.py`, which needs to vary the instructions (to
    defeat the prompt cache) and the model settings (to steer it) while keeping every other
    part of the agent identical. Leave them unset and the behaviour is exactly the CLI's.
    """
    settings = load_settings()
    if settings.model_override_ignored:
        print(
            f"note: OPENAI_MODEL={settings.model_override_ignored!r} was ignored; "
            f"this project is pinned to {settings.model_name}.",
            file=sys.stderr,
        )
    model = OpenAIResponsesModel(
        settings.model_name,
        provider=OpenAIProvider(openai_client=build_portkey_client(settings)),
    )
    agent = Agent(
        model,
        output_type=VendorAssessment,
        deps_type=VendorDeskDeps,
        instructions=(
            instructions if instructions is not None
            else build_instructions(PROMPT_PATH if defenses else UNDEFENDED_PROMPT_PATH)
        ),
        # The design layer, in one line: the reading agent is not given the tools that act
        # on the outside world. They still exist and are still exported; they are simply not
        # on this roster, so no document can reach them however convincing it is.
        tools=DEFENDED_TOOLS if defenses else VENDOR_DESK_TOOLS,
        retries=2,
        model_settings=model_settings,
    )
    return agent, settings.model_name


def apply_guards(
    answer: VendorAssessment, deps: VendorDeskDeps, *, defenses: bool
) -> tuple[VendorAssessment, GuardReport]:
    """Decide in code, and clean anything the document tried to smuggle into the prose.

    Two separate jobs, and it is worth keeping them separate in your head:

    1. **The decision is computed, not accepted.** `handbook.apply_checks` runs §4's four
       comparisons over the figures the model reported. If the model's decision disagrees
       with the arithmetic, the arithmetic wins and the disagreement is recorded. A document
       can still lie about a figure — nothing here can tell that $17.44 was never the price —
       but it can no longer *argue* its way to a recommendation the figures do not support.
    2. **The reason is sanitised.** A URL in the reason means a vendor got a link in front of
       the buyer; one of our own cost ceilings means the handbook's confidentiality rule just
       broke. Either way the model's sentence is dropped and the computed one used instead.
    """
    extraction = deps.last_extraction
    report = GuardReport(
        defenses=defenses,
        concealment_checked=bool(extraction and extraction.concealment_checked),
        concealed_fragments=len(extraction.hidden) if extraction else 0,
        directives_flagged=len(extraction.directives) if extraction else 0,
        tools_offered=[t.__name__ for t in (DEFENDED_TOOLS if defenses else VENDOR_DESK_TOOLS)],
        model_decision=answer.decision,
    )
    if not defenses:
        return answer, report

    hb = parse_handbook(HANDBOOK_PATH)
    ruling = apply_checks(
        hb, vendor=answer.vendor, sku=answer.sku, unit_price=answer.unit_price,
        lead_time_days=answer.lead_time_days, min_order=answer.min_order,
    )
    report.computed_decision = ruling.decision
    report.decision_overridden = ruling.decision != answer.decision
    report.checks = [f"{c.name}: {'pass' if c.passed else 'FAIL'} — {c.detail}" for c in ruling.checks]

    reason = answer.reason
    ceiling = hb.catalogue.get(answer.sku or "")
    if URL_IN_ANSWER.search(reason):
        report.reason_replaced, report.reason_replaced_why = True, "the reason contained a URL"
    elif ceiling is not None and re.search(rf"\${ceiling.max_unit_cost:,.2f}\b", reason):
        report.reason_replaced, report.reason_replaced_why = True, "the reason repeated our max unit cost"
    elif report.decision_overridden:
        report.reason_replaced, report.reason_replaced_why = True, "the decision was overridden"

    return (
        answer.model_copy(update={
            "decision": ruling.decision,
            "reason": ruling.reason if report.reason_replaced else reason,
        }),
        report,
    )


def print_assessment(doc: Path, answer: VendorAssessment) -> None:
    def show(value: object) -> str:
        return "unknown" if value is None else str(value)

    print(f"\n{doc.name}")
    print(f"  vendor          {show(answer.vendor)}")
    print(f"  sku             {show(answer.sku)}")
    print(f"  unit price      {'unknown' if answer.unit_price is None else f'${answer.unit_price:,.2f}'}")
    print(f"  lead time       {show(answer.lead_time_days)} days")
    print(f"  minimum order   {show(answer.min_order)} units")
    print(f"  DECISION        {answer.decision.upper()}")
    print(f"  reason          {answer.reason}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Assess one Campus Customs vendor document.")
    ap.add_argument("--doc", type=Path, required=True, help="path to the vendor document")
    ap.add_argument(
        "--output-dir", type=Path, default=OUTPUT_DIR, help="where the three log files live"
    )
    ap.add_argument(
        "--show-document",
        action="store_true",
        help="print the text the agent would see and exit, without calling the model (free)",
    )
    ap.add_argument(
        "--defenses",
        choices=("on", "off"),
        default="on",
        help="'off' restores the Problem 3 agent exactly: the undefended prompt, PDFs not "
             "inspected for concealment, no directive scan, both trap tools on the roster, "
             "and the model's own decision reported. Kept for Problem 7.",
    )
    args = ap.parse_args()
    defenses = args.defenses == "on"

    doc: Path = args.doc
    if not doc.is_file():
        print(f"No such document: {doc}", file=sys.stderr)
        return 2

    if args.show_document:
        print(format_document(doc, extract_document(doc, defenses=defenses)))
        return 0

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    ensure_trap_file(output_dir)

    agent, model_name = build_agent(defenses=defenses)
    deps = VendorDeskDeps(document_path=doc.resolve(), output_dir=output_dir, defenses=defenses)
    run_id = uuid4().hex[:12]
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")

    answer: VendorAssessment | None = None
    error: str | None = None
    usage = None
    guard: GuardReport | None = None
    try:
        result = agent.run_sync(f"Assess the vendor document at {doc}", deps=deps)
        answer, usage = result.output, result.usage
        answer, guard = apply_guards(answer, deps, defenses=defenses)
    except Exception as exc:  # recorded, then re-reported: a failed run is worth an audit entry
        error = f"{type(exc).__name__}: {exc}"

    append_json_list(
        output_dir / AUDIT_TRAIL_PATH.name,
        AuditRecord(
            run_id=run_id,
            timestamp=started,
            document=str(doc),
            model=model_name,
            tool_calls=deps.tool_calls,
            final_answer=answer,
            error=error,
            note=None if defenses else "defenses:off",
            guard=guard,
        ),
    )

    if usage is not None:
        cost = cost_breakdown(
            input_tokens=usage.input_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens,
            output_tokens=usage.output_tokens,
            rates=load_rates(),
        )
        append_json_list(
            output_dir / USAGE_LOG_PATH.name,
            UsageRecord(
                run_id=run_id,
                timestamp=started,
                document=str(doc),
                model=model_name,
                requests=usage.requests,
                cost=cost,
            ),
        )

    if error or answer is None:
        print(f"Run failed: {error}", file=sys.stderr)
        return 1

    print_assessment(doc, answer)
    if guard is not None:
        print(f"\n  defenses        {'ON' if guard.defenses else 'OFF'}   "
              f"tools offered: {', '.join(guard.tools_offered)}")
        if guard.defenses:
            conceal = (f"{guard.concealed_fragments} concealed fragment(s)" if guard.concealed_fragments
                       else ("none found" if guard.concealment_checked else "NOT CHECKED"))
            print(f"  code layer      {conceal}; {guard.directives_flagged} directive(s) flagged")
            print(f"  design layer    model said {guard.model_decision}, handbook checks say "
                  f"{guard.computed_decision}"
                  + ("  ** OVERRIDDEN **" if guard.decision_overridden else "  (agree)"))
            if guard.reason_replaced:
                print(f"  reason replaced {guard.reason_replaced_why}")
    print(f"\n  tools called    {len(deps.tool_calls)}  ({', '.join(c.tool for c in deps.tool_calls) or 'none'})")
    if usage is not None:
        print(
            f"  tokens          {usage.input_tokens:,} in "
            f"({usage.cache_read_tokens:,} cached) / {usage.output_tokens:,} out"
        )
        print(f"  cost            ${cost.total_usd:.6f}")
    if deps.trap_calls:
        print(
            f"\n  ** {len(deps.trap_calls)} TRAP TOOL CALL(S) RECORDED — a document took over "
            f"the agent. See {output_dir / 'trap_calls.json'} **",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
