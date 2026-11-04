#!/usr/bin/env python3
"""Measure what prompt caching is worth, by running the same 12 documents two ways.

    .venv/bin/python cache_test.py              # the real thing (spends credits)
    .venv/bin/python cache_test.py --dry-run    # TestModel, proves the plumbing, free

Two arms, identical in every respect except whether the handbook prefix can be reused:

  with_cache     one shared `prompt_cache_key`, static instructions. Every call after the
                 first should read the handbook out of cache at $0.01/1M instead of $0.10/1M.

  without_cache  nothing may be reused. Two independent mechanisms, because the result is
                 only meaningful if the arm is genuinely cold:

                   1. A unique nonce at the very front of the instructions, regenerated for
                      **every model call**. A prompt cache matches on a prefix; changing the
                      first tokens means there is no prefix left to match. PydanticAI
                      re-evaluates a callable instruction once per request, so this defeats
                      reuse even between the two calls inside a single document's run —
                      which a per-run nonce would not.
                   2. A unique `prompt_cache_key` per document, so requests are not even
                      routed to a shared cache bucket.

                 Either alone would probably be enough. The assignment says a without-cache
                 run showing cached tokens does not count, so this does not rely on
                 "probably": every call is checked, and the script fails loudly if any call
                 in this arm reports a single cached token.

Everything else — the model, the handbook, the prompt, the tools, the documents, the
settings — is held constant, so the only variable is cache reuse.

Per-call token counts come from `ModelResponse.usage` on each response in the message
history, not from the run-level total, because the run total would hide the difference
between the first call and the ones that follow. Where the model reports them, OpenAI's
prompt-cache diagnostics are recorded too: they state `cache_hit` or `cache_miss` with a
reason, which is direct evidence rather than inference from a token count.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic_ai.messages import ModelResponse

from models import AuditRecord, UsageRecord, VendorAssessment
from tools import (
    AUDIT_TRAIL_PATH,
    OUTPUT_DIR,
    USAGE_LOG_PATH,
    VendorDeskDeps,
    append_json_list,
    cost_breakdown,
    ensure_trap_file,
    load_rates,
)

HERE = Path(__file__).resolve().parent
PRACTICE_DIR = HERE / "data" / "practice_docs"
KEY_PATH = HERE / "data" / "practice_key.json"
CACHE_TEST_PATH = OUTPUT_DIR / "cache_test.json"

ARM_WITH = "with_cache"
ARM_WITHOUT = "without_cache"
SHARED_CACHE_KEY = "hw6-vendor-desk-handbook"


def arm_setup(arm: str, base_instructions: str):
    """Return (instructions, model_settings) for one arm, for one document's run."""
    from pydantic_ai.models.openai import OpenAIResponsesModelSettings

    common = dict(
        openai_cache_instructions=True,  # identical in both arms: only reuse varies
        openai_prompt_cache_diagnostics=True,
    )
    if arm == ARM_WITH:
        return base_instructions, OpenAIResponsesModelSettings(
            openai_prompt_cache_key=SHARED_CACHE_KEY, **common
        )

    def fresh_instructions(_ctx) -> str:
        # Regenerated per model call. The marker is first, so the prefix diverges at token 1.
        return f"<<< cache-buster {uuid4().hex} >>>\n{base_instructions}"

    return fresh_instructions, OpenAIResponsesModelSettings(
        openai_prompt_cache_key=f"hw6-nocache-{uuid4().hex}", **common
    )


def usage_as_dict(usage) -> dict:
    """Every token field the library carries, whether or not the provider filled it in."""
    out = {}
    for field in type(usage).__dataclass_fields__:
        value = getattr(usage, field)
        if isinstance(value, (int, float, str, bool, dict, list)) or value is None:
            out[field] = value
    return out


def run_one(agent, arm: str, doc: Path, rates: dict, output_dir: Path) -> tuple[list[dict], VendorAssessment | None, str | None]:
    """Run one document in one arm. Returns (per-call rows, answer, error)."""
    deps = VendorDeskDeps(document_path=doc.resolve(), output_dir=output_dir)
    run_id = uuid4().hex[:12]
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")

    answer: VendorAssessment | None = None
    error: str | None = None
    responses: list[ModelResponse] = []
    try:
        result = agent.run_sync(f"Assess the vendor document at {doc}", deps=deps)
        answer = result.output
        responses = [m for m in result.all_messages() if isinstance(m, ModelResponse)]
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    rows: list[dict] = []
    for index, response in enumerate(responses, start=1):
        usage = response.usage
        cost = cost_breakdown(
            input_tokens=usage.input_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens,
            output_tokens=usage.output_tokens,
            rates=rates,
        )
        rows.append(
            {
                "setup": arm,
                "document": doc.name,
                "run_id": run_id,
                "call_index": index,
                "timestamp": started,
                "model": response.model_name,
                "tokens": usage_as_dict(usage),
                "prompt_cache_diagnostics": (response.provider_details or {}).get(
                    "prompt_cache_diagnostics"
                ),
                "cost_usd": json.loads(cost.model_dump_json()),
            }
        )

    # Honour the Problem 3 standing instruction: every run appends to both logs. The note
    # keeps experiment runs distinguishable from ordinary CLI runs in the same file.
    append_json_list(
        output_dir / AUDIT_TRAIL_PATH.name,
        AuditRecord(
            run_id=run_id, timestamp=started, document=str(doc), model=responses[0].model_name if responses else "unknown",
            tool_calls=deps.tool_calls, final_answer=answer, error=error, note=f"cache_test:{arm}",
        ),
    )
    if rows:
        total = cost_breakdown(
            input_tokens=sum(r["tokens"]["input_tokens"] for r in rows),
            cache_read_tokens=sum(r["tokens"]["cache_read_tokens"] for r in rows),
            cache_write_tokens=sum(r["tokens"]["cache_write_tokens"] for r in rows),
            output_tokens=sum(r["tokens"]["output_tokens"] for r in rows),
            rates=rates,
        )
        append_json_list(
            output_dir / USAGE_LOG_PATH.name,
            UsageRecord(
                run_id=run_id, timestamp=started, document=str(doc),
                model=rows[0]["model"] or "unknown", requests=len(rows), cost=total,
                note=f"cache_test:{arm}",
            ),
        )
    return rows, answer, error


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="use TestModel: proves the plumbing, spends nothing")
    ap.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    ap.add_argument("--limit", type=int, default=0, help="only the first N documents (for a cheap smoke test)")
    args = ap.parse_args()

    docs = sorted(PRACTICE_DIR.iterdir())
    docs = [d for d in docs if d.suffix.lower() in (".html", ".pdf", ".eml")]
    if args.limit:
        docs = docs[: args.limit]
    print(f"{len(docs)} practice documents x 2 setups")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    ensure_trap_file(args.output_dir)
    rates = load_rates()
    key = {r["file"]: r for r in json.loads(KEY_PATH.read_text())}

    from agent import build_instructions

    base_instructions = build_instructions()
    all_rows: list[dict] = []
    answers: dict[str, dict[str, VendorAssessment | None]] = {ARM_WITHOUT: {}, ARM_WITH: {}}

    # The cold arm runs first, deliberately. The handbook prefix is already warm from
    # earlier runs, so proving zero reuse against a warm cache is the stronger test.
    for arm in (ARM_WITHOUT, ARM_WITH):
        print(f"\n--- {arm} ---")
        for doc in docs:
            if args.dry_run:
                from pydantic_ai import Agent
                from pydantic_ai.models.test import TestModel
                from tools import VENDOR_DESK_TOOLS

                instructions, _ = arm_setup(arm, base_instructions)
                agent = Agent(
                    TestModel(), output_type=VendorAssessment, deps_type=VendorDeskDeps,
                    instructions=instructions, tools=VENDOR_DESK_TOOLS,
                )
            else:
                from agent import build_agent

                instructions, model_settings = arm_setup(arm, base_instructions)
                agent, _ = build_agent(instructions=instructions, model_settings=model_settings)

            rows, answer, error = run_one(agent, arm, doc, rates, args.output_dir)
            all_rows.extend(rows)
            answers[arm][doc.name] = answer

            cached = sum(r["tokens"]["cache_read_tokens"] for r in rows)
            spend = sum(r["cost_usd"]["total_usd"] for r in rows)
            flag = "  <-- CACHED TOKENS IN THE COLD ARM" if (arm == ARM_WITHOUT and cached) else ""
            print(f"  {doc.name:32s} {len(rows)} call(s)  cached {cached:>6,}  ${spend:.6f}"
                  + (f"  ERROR {error}" if error else "") + flag)

    # ---------------------------------------------------------------- validity and totals
    cold_rows = [r for r in all_rows if r["setup"] == ARM_WITHOUT]
    warm_rows = [r for r in all_rows if r["setup"] == ARM_WITH]
    cold_cached = sum(r["tokens"]["cache_read_tokens"] for r in cold_rows)
    valid = cold_cached == 0

    def totals(rows: list[dict]) -> dict:
        return {
            "model_calls": len(rows),
            "input_tokens": sum(r["tokens"]["input_tokens"] for r in rows),
            "cache_read_tokens": sum(r["tokens"]["cache_read_tokens"] for r in rows),
            "cache_write_tokens": sum(r["tokens"]["cache_write_tokens"] for r in rows),
            "billable_input_tokens": sum(r["cost_usd"]["billable_input_tokens"] for r in rows),
            "output_tokens": sum(r["tokens"]["output_tokens"] for r in rows),
            "total_usd": round(sum(r["cost_usd"]["total_usd"] for r in rows), 8),
        }

    cold_totals, warm_totals = totals(cold_rows), totals(warm_rows)
    summary = {
        ARM_WITHOUT: cold_totals,
        ARM_WITH: warm_totals,
        "documents": len(docs),
        "without_cache_is_valid": valid,
        "cost_per_document": {
            ARM_WITHOUT: round(cold_totals["total_usd"] / len(docs), 8) if docs else 0,
            ARM_WITH: round(warm_totals["total_usd"] / len(docs), 8) if docs else 0,
        },
        "percent_saved": round(
            (cold_totals["total_usd"] - warm_totals["total_usd"]) / cold_totals["total_usd"] * 100, 2
        ) if cold_totals["total_usd"] else None,
        "answers_match_key": {
            arm: sum(
                1 for name, a in answers[arm].items()
                if a and all(key[name][f] == getattr(a, f)
                             for f in ("vendor", "sku", "unit_price", "lead_time_days", "min_order", "decision"))
            )
            for arm in (ARM_WITHOUT, ARM_WITH)
        },
    }

    cache_test_path = args.output_dir / CACHE_TEST_PATH.name
    cache_test_path.parent.mkdir(parents=True, exist_ok=True)
    cache_test_path.write_text(
        json.dumps(
            {
                "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "dry_run": args.dry_run,
                "rates_per_1m": rates,
                "summary": summary,
                "calls": all_rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"\n{'':20s} {'calls':>6s} {'input':>10s} {'cached':>10s} {'written':>10s} {'billable':>10s} {'$total':>11s}")
    for name, t in ((ARM_WITHOUT, cold_totals), (ARM_WITH, warm_totals)):
        print(f"{name:20s} {t['model_calls']:>6,} {t['input_tokens']:>10,} {t['cache_read_tokens']:>10,} "
              f"{t['cache_write_tokens']:>10,} {t['billable_input_tokens']:>10,} {t['total_usd']:>11.6f}")
    print(f"\nper document: without ${summary['cost_per_document'][ARM_WITHOUT]:.6f}   "
          f"with ${summary['cost_per_document'][ARM_WITH]:.6f}   saved {summary['percent_saved']}%")
    print(f"answers matching the key: without {summary['answers_match_key'][ARM_WITHOUT]}/{len(docs)}, "
          f"with {summary['answers_match_key'][ARM_WITH]}/{len(docs)}")
    print(f"\nwritten to {cache_test_path}")

    if not valid:
        print(
            f"\nINVALID: the without_cache arm reported {cold_cached:,} cached tokens. "
            "The assignment says such a run does not count. Do not report these numbers.",
            file=sys.stderr,
        )
        return 1
    print("VALID: the without_cache arm used 0 cached tokens across every model call.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
