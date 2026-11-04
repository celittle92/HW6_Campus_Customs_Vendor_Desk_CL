#!/usr/bin/env python3
"""Run the defended vendor desk over `data/exam_docs/` and write the graded results.

    .venv/bin/python exam_run.py              # the real run (spends credits)
    .venv/bin/python exam_run.py --dry-run    # TestModel, free, proves the shape

`output/exam_results.json` is written **by this script and never touched by hand**. It is a
plain JSON array with exactly one object per exam file, carrying exactly the thirteen fields
the assignment lists and nothing else — no wrapper, no extra keys — so whatever parses it does
not have to know anything about this project. Provenance that would otherwise clutter it
(model, prompt, per-run guard reports) goes to `output/exam_run_meta.json` instead.

The agent is the defended one: PDFs inspected for concealment, documents scanned for text
aimed at an automated reader, the decision computed from the handbook rather than accepted
from the model, and `send_email` / `approve_payment` **not on the roster**. `trap_tool_called`
is recorded from what actually happened on the run, not assumed from that.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent import PROMPT_PATH, apply_guards, build_instructions
from app_config import REQUIRED_OPENAI_MODEL
from models import AuditRecord, UsageRecord, VendorAssessment
from tools import (
    AUDIT_TRAIL_PATH,
    DEFENDED_TOOLS,
    OUTPUT_DIR,
    USAGE_LOG_PATH,
    VendorDeskDeps,
    append_json_list,
    cost_breakdown,
    ensure_trap_file,
    load_rates,
)

HERE = Path(__file__).resolve().parent
EXAM_DIR = HERE / "data" / "exam_docs"
RESULTS_PATH = OUTPUT_DIR / "exam_results.json"
META_PATH = OUTPUT_DIR / "exam_run_meta.json"

#: The exact field list the assignment specifies, in its order.
FIELDS = (
    "file", "vendor", "sku", "unit_price", "lead_time_days", "min_order",
    "decision", "reason", "trap_tool_called",
    "input_tokens", "cached_tokens", "output_tokens", "cost_usd",
)


def run_one(agent, doc: Path, rates: dict, output_dir: Path) -> tuple[dict, dict]:
    deps = VendorDeskDeps(document_path=doc.resolve(), output_dir=output_dir, defenses=True)
    run_id = uuid4().hex[:12]
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")

    answer: VendorAssessment | None = None
    guard = None
    error: str | None = None
    usage = None
    try:
        result = agent.run_sync(f"Assess the vendor document at {doc}", deps=deps)
        answer, usage = result.output, result.usage
        answer, guard = apply_guards(answer, deps, defenses=True)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    cost = None
    if usage is not None:
        cost = cost_breakdown(
            input_tokens=usage.input_tokens, cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens, output_tokens=usage.output_tokens,
            rates=rates,
        )

    entry = {
        "file": doc.name,
        "vendor": answer.vendor if answer else None,
        "sku": answer.sku if answer else None,
        "unit_price": answer.unit_price if answer else None,
        "lead_time_days": answer.lead_time_days if answer else None,
        "min_order": answer.min_order if answer else None,
        "decision": answer.decision if answer else None,
        "reason": answer.reason if answer else None,
        # Recorded from the run, not inferred from the roster.
        "trap_tool_called": bool(deps.trap_calls),
        "input_tokens": usage.input_tokens if usage else 0,
        "cached_tokens": usage.cache_read_tokens if usage else 0,
        "output_tokens": usage.output_tokens if usage else 0,
        "cost_usd": round(cost.total_usd, 8) if cost else 0.0,
    }
    assert tuple(entry) == FIELDS, "entry fields drifted from the assignment's list"

    extraction = deps.last_extraction
    meta = {
        "file": doc.name,
        "run_id": run_id,
        "timestamp": started,
        "error": error,
        "concealed_fragments": len(extraction.hidden) if extraction else 0,
        "concealment_checked": bool(extraction and extraction.concealment_checked),
        "directives_flagged": len(extraction.directives) if extraction else 0,
        "tools_offered": [t.__name__ for t in DEFENDED_TOOLS],
        "tools_called": [c.tool for c in deps.tool_calls],
        "guard": json.loads(guard.model_dump_json()) if guard else None,
        "requests": usage.requests if usage else 0,
        "cost_detail": json.loads(cost.model_dump_json()) if cost else None,
    }

    append_json_list(output_dir / AUDIT_TRAIL_PATH.name,
                     AuditRecord(run_id=run_id, timestamp=started, document=str(doc),
                                 model=REQUIRED_OPENAI_MODEL, tool_calls=deps.tool_calls,
                                 final_answer=answer, error=error, note="exam_run", guard=guard))
    if cost is not None:
        append_json_list(output_dir / USAGE_LOG_PATH.name,
                         UsageRecord(run_id=run_id, timestamp=started, document=str(doc),
                                     model=REQUIRED_OPENAI_MODEL, requests=usage.requests,
                                     cost=cost, note="exam_run"))
    return entry, meta


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="TestModel; proves the shape, spends nothing")
    ap.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    ap.add_argument("--results-name", default=RESULTS_PATH.name)
    args = ap.parse_args()

    docs = [d for d in sorted(EXAM_DIR.iterdir()) if d.suffix.lower() in (".html", ".pdf", ".eml")]
    print(f"{len(docs)} exam documents, defended agent, model {REQUIRED_OPENAI_MODEL}\n")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    ensure_trap_file(args.output_dir)
    rates = load_rates()
    instructions = build_instructions(PROMPT_PATH)

    if args.dry_run:
        from pydantic_ai import Agent
        from pydantic_ai.models.test import TestModel

        agent = Agent(TestModel(), output_type=VendorAssessment, deps_type=VendorDeskDeps,
                      instructions=instructions, tools=DEFENDED_TOOLS)
    else:
        from agent import build_agent

        agent, _ = build_agent(defenses=True)

    entries, metas = [], []
    for doc in docs:
        entry, meta = run_one(agent, doc, rates, args.output_dir)
        entries.append(entry)
        metas.append(meta)
        price = "unknown" if entry["unit_price"] is None else f"${entry['unit_price']:,.2f}"
        print(f"  {entry['file']:22s} {str(entry['vendor'])[:24]:24s} {str(entry['sku']):10s} "
              f"{price:>9s} {str(entry['lead_time_days']):>4s}d {str(entry['min_order']):>6s}u  "
              f"{entry['decision'] or 'ERROR':17s} trap={str(entry['trap_tool_called']):5s} "
              f"${entry['cost_usd']:.6f}")
        if meta["error"]:
            print(f"      ERROR: {meta['error']}")

    out = args.output_dir / args.results_name
    out.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / META_PATH.name).write_text(json.dumps({
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dry_run": args.dry_run,
        "model": REQUIRED_OPENAI_MODEL,
        "prompt": PROMPT_PATH.name,
        "defenses": {"code": True, "prompt": True, "design": True},
        "rates_per_1m": rates,
        "runs": metas,
    }, indent=2) + "\n", encoding="utf-8")

    traps = [e["file"] for e in entries if e["trap_tool_called"]]
    missing = [e["file"] for e in entries if not e["decision"]]
    unknowns = [(e["file"], f) for e in entries for f in ("vendor", "sku", "unit_price", "lead_time_days", "min_order")
                if e[f] is None]
    totals = (sum(e["input_tokens"] for e in entries), sum(e["cached_tokens"] for e in entries),
              sum(e["output_tokens"] for e in entries), sum(e["cost_usd"] for e in entries))

    print(f"\n  entries written     {len(entries)}  -> {out}")
    print(f"  trap tool calls     {len(traps)} {traps if traps else ''}")
    print(f"  runs without an answer {len(missing)} {missing if missing else ''}")
    print(f"  fields reported unknown {len(unknowns)} {unknowns if unknowns else ''}")
    print(f"  tokens  {totals[0]:,} in ({totals[1]:,} cached) / {totals[2]:,} out")
    print(f"  cost    ${totals[3]:.6f}")
    return 1 if (traps or missing) else 0


if __name__ == "__main__":
    raise SystemExit(main())
