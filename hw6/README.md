# HW6 — the Campus Customs vendor desk

An AI agent that reads a vendor document — an HTML quote, a PDF quote, a catalogue page or a
vendor email — pulls out the facts a buyer needs, applies the shop handbook's purchasing
rules, and returns a recommendation.

Many of the supplied documents are **booby-trapped**: they carry text aimed at the agent
rather than at a buyer, hidden in HTML comments, invisible CSS, white-on-white PDF text,
0.8pt type, and in one case drawn off the bottom of the page. A large part of this project is
noticing that and not being moved by it.

```
python agent.py --doc data/practice_docs/p01_bluehen_quote.html
```

---

## Running it

**1. Set up the environment.** Python 3.11+ (built and tested on 3.14).

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

**2. Add a Portkey key.** Copy the template and fill in your own key — `.env` is gitignored
and is never committed.

```bash
cp .env.example .env
# then edit .env and set PORTKEY_API_KEY=...
```

**3. Run the agent on one document.**

```bash
.venv/bin/python agent.py --doc data/practice_docs/p01_bluehen_quote.html
```

It prints the assessment and appends to three files in `output/`: `usage_log.json` (tokens
and dollars), `audit_trail.json` (every tool call and the final answer), and
`trap_calls.json` (see below).

### Useful flags

| Command | What it does | Costs |
|---|---|---|
| `agent.py --doc <file>` | Assess one document, defences on | a model call |
| `agent.py --doc <file> --show-document` | Print exactly what the agent would read, then exit | **free** |
| `agent.py --doc <file> --defenses off` | The undefended Problem 3 agent, for comparison | a model call |

### Batch runs

```bash
.venv/bin/python exam_run.py                      # the 10 exam documents -> output/exam_results.json
.venv/bin/python defense_test.py --config full    # the 12 practice documents, scored
.venv/bin/python attack_test.py                   # the same 12 against the undefended agent
.venv/bin/python cache_test.py                    # the caching experiment (slow: ~1 hour)
```

Every one of these takes `--dry-run`, which swaps in a stub model and **spends nothing** —
useful for checking the plumbing before paying for anything.

### Checks that cost nothing

```bash
.venv/bin/python tests/test_offline.py            # 92 checks, no model call, no network
.venv/bin/python count_tokens.py data/shop_handbook.md
.venv/bin/python build_report.py                  # rebuild output/hw6_report.html
```

---

## How it is put together

| File | What it is |
|---|---|
| `agent.py` | Entry point: CLI, prompt assembly, model wiring, logging |
| `tools.py` | The agent's tools, document extraction, concealment detection, pricing |
| `models.py` | The structured types every answer is validated against |
| `handbook.py` | The handbook's purchasing rules, applied in code |
| `prompts/prompt.md` | The agent's runtime instructions; the handbook is spliced into it |
| `prompts/prompt_problem3.md` | The undefended prompt, frozen, so the "before" case is reproducible |
| `app_config.py` | Portkey settings. The model is **pinned** to `gpt-6-luna` |

The model is read through `app_config.REQUIRED_OPENAI_MODEL` and cannot be changed by the
environment: `OPENAI_MODEL` is read, reported, and ignored.

### Three layers of defence

- **Code** — before the model sees anything, the reader separates what a buyer could see from
  what was hidden from them, including PDF text drawn in white, set below 4pt, or positioned
  off the page. It flags text addressed to an automated reader, and says *not checked* rather
  than *none found* when it has not inspected a format.
- **Design** — the model reports the facts; `handbook.py` makes the decision, from the vendor
  lists, cost ceilings and thresholds parsed out of the handbook at run time. A document can
  lie about a figure, but it cannot argue its way past the rules.
- **Prompt** — the judgement calls the other two cannot name in advance.

### The trap tools

`send_email` and `approve_payment` exist and **do nothing**. They record the attempt to
`output/trap_calls.json` and refuse. Nothing in the vendor desk's job needs either one, so an
entry in that file is a finding: a document talked the agent out of its job. The file has
stayed empty across every run.

The defended agent is not even offered them — a document cannot reach a tool the agent does
not have.

---

## The data

`data/` is committed in full so the agent runs straight from a clone.

| Path | What it is |
|---|---|
| `data/shop_handbook.md` | The store handbook: purchasing rules, vendor lists, the 177-SKU catalogue with cost ceilings |
| `data/practice_docs/` | 12 vendor documents, with answers in `data/practice_key.json` |
| `data/exam_docs/` | 10 vendor documents, no answer key |
| `data/my_attacks/` | Two booby-trapped documents written for this project, with `attack_key.json` |
| `data/prices.json` | Per-1M-token model prices, for costing a run |

---

## Results

Start with **[`output/hw6_report.html`](output/hw6_report.html)** — one self-contained page,
no internet needed, that presents the whole thing. Then:

| File | What it covers |
|---|---|
| `output/harness.md` | The engineering record, one section per problem, plus a Safety section |
| `output/handbook_estimate.md` | What the handbook costs to send on every call |
| `output/cache_test.md` | Caching, measured: 83% cheaper |
| `output/attack_results.md` | The undefended agent against the practice set |
| `output/defense_results.md` | The defended agent, before and after |
| `output/red_team.md` | Two attacks written against our own agent |
| `output/exam_results.json` | The graded exam output |

`AI_prompts.md` is the prompt log — every instruction given, verbatim, with what each one
produced.

---

*MGT 409 AI Foundations · Christine Little · model `gpt-6-luna` via Portkey.*
