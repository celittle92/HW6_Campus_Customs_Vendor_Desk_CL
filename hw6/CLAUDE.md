# HW6 project memory

Authoritative rules for this folder live in `.claude/rules/hw6-vendor-desk.md`, **two**
levels up in the private AI Foundations course workspace. The import below resolves only
inside that workspace, not in a standalone clone of this repo. Read that file, plus `AI_prompts.md` and
`output/harness.md`, before changing anything here.

@../../.claude/rules/hw6-vendor-desk.md

## Local facts

- There is no written assignment brief. Christine types each problem in her own words as
  the work goes, the way HW3 and HW5 went. Each problem gets a section in `AI_prompts.md`
  (her prompts, verbatim) and in `output/harness.md` (the engineering).
- **Where this folder sits.** The public git repo is the parent,
  `HW6_Campus_Customs_Vendor_Desk_CL/`, and it holds exactly one thing: this `hw6/` — the
  HW4 and HW5 layout, which the assignment's file tree shows. So the course workspace root
  is **two** levels up, and commands run from there need the
  `HW6_Campus_Customs_Vendor_Desk_CL/hw6/...` prefix. Moved there from `hw6/` on 2026-11-04
  for Problem 10.
- **The repo is live and public** at
  <https://github.com/celittle92/HW6_Campus_Customs_Vendor_Desk_CL>, pushed 2026-11-04;
  `output/github_url.txt` holds the URL. Anything committed here is published as soon as
  it is pushed — **ask before every push**. The parent folder is its own git repo,
  gitignored in the private workspace (the HW4/HW5 pattern). Git writes and `gh` need the
  Terminal panel; `gh` is at `../../.tools/gh/bin/gh`.
- **HW6 is self-contained.** Christine's instruction, 2026-11-03: the only data this
  homework uses is `hw6/data/`. Nothing comes from HW3, HW4, or HW5 — HW4 and HW5 are also
  Campus Customs and HW5 even has its own `campus_customs.db`, but the shop name is all
  they share with this one. See the rule file for the full statement.
- **The supplied data pack is already unpacked** into `data/`, from `data (1).zip` in this
  folder:
  - `data/shop_handbook.md` — 338 lines, 13 sections. §4 purchasing rules, §5 approved
    vendors, §6 removed/pending vendors, §9 the 177-SKU catalogue with max unit costs,
    §10 the last 12 months of purchase orders, §13 the required report fields.
  - `data/practice_docs/` — 12 documents: 5 HTML (4 quotes + 1 catalog page), 4 PDF
    quotes, 3 `.eml` vendor emails.
  - `data/practice_key.json` — the answer key for those 12, one object each with `file`,
    `vendor`, `sku`, `unit_price`, `lead_time_days`, `min_order`, `decision`. Both
    decisions appear in it.
  - `data/exam_docs/` — 10 documents in the same mix (4 HTML, 3 PDF, 3 `.eml`), **with
    no key**.
  - `data/prices.json` — per-1M-token prices for `gpt-6-luna` (input, cached input, cache
    write, output), cited to OpenAI Standard pricing, MGT 409 Lecture 11.
- **The model is pinned to `gpt-6-luna`** in `app_config.py` (`REQUIRED_OPENAI_MODEL`),
  settled on 2026-11-03: any other model loses marks. `OPENAI_MODEL` is still read but
  cannot win, and neither can a `model_override=` argument; the ignored value is reported
  on `Settings.model_override_ignored`. This matters because the semester default in
  `AGENT.MD` is `gpt-5.6-luna`, so a stray `OPENAI_MODEL` in the shared workspace `.env`
  would otherwise bill the wrong model silently. `data/prices.json` prices `gpt-6-luna`
  too, so cost figures match what is billed.
- `gpt-6-luna` returns HTTP 400 for tool calls on the chat-completions endpoint. If HW6
  gives the model tools, use PydanticAI's `OpenAIResponsesModel`, not the default
  chat-completions model class.
- `PORTKEY_API_KEY` comes from the shared workspace-root `.env` through `app_config.py`,
  which loads a project `.env` first and falls back to the workspace one. **No per-project
  `.env` is needed**; `.env.example` lists the names only. The sandbox cannot read `.env`,
  so live connection checks are Christine's to run from the Terminal panel.
- The course Portkey key hit its usage limit on 2026-10-04 (HTTP 412 on HW3). Confirm it
  was raised before planning any paid run.
- **The venv exists** (built 2026-11-03, Python 3.14.7) with `requirements.txt` installed:
  pydantic-ai-slim 2.65.0, openai 3.44.0, pypdf 6.21.4, python-dotenv 1.2.4. The system
  `python3` is also 3.14.7, so it runs `check_submission.py` and any plain-stdlib script
  here; use the venv for anything importing the project's dependencies. `python` is not on
  PATH on this machine. Rebuild from the **Terminal panel**, not sandboxed Bash — the
  sandbox blocks the `.pem` that pip writes during `ensurepip`:

  ```bash
  cd "/Users/christinelittle/Yale SOM_Old/AI Foundations/HW6_Campus_Customs_Vendor_Desk_CL/hw6"
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
  ```

- Environment smoke check (free, no API calls), from this folder:
  `.venv/bin/python -c "import pydantic_ai, dotenv, pypdf, openai"`
- **Token counting:** `.venv/bin/python count_tokens.py <file> [--calls N]` (free, no model
  call). `tiktoken` has no table for `gpt-6-luna`, so it uses `o200k_base` as the closest
  published encoding; `cl100k_base` comes out 1.3% higher, which is the size of the
  uncertainty. The script pins `TIKTOKEN_CACHE_DIR` to `hw6/.tiktoken_cache/` (gitignored)
  so counts are reproducible. **Its first run per encoding needs network and must go
  through the Terminal panel** — the sandbox denies reading certifi's `cacert.pem`, so
  `tiktoken`'s download fails there with a TLS CA error. Once cached, sandboxed Bash runs
  it fine. `o200k_base` and `cl100k_base` are both cached already.
- The handbook is **10,058 tokens** (`o200k_base`); §9 the catalogue is 69% of that and
  §10 the purchase orders another 15%. `output/handbook_estimate.md` has the costs.
- `data/shop_handbook.md` has **CRLF line endings**. Python text mode folds them to `\n`
  (10,058 tokens); byte-for-byte with the carriage returns it is 10,069. That is also why
  `wc -c` says 29,241 bytes but the file is 28,903 characters.
- Pre-submission check, from the workspace root (offline, no API calls; FAILs are the
  to-do list until each piece is built):
  `python3 check_submission.py HW6_Campus_Customs_Vendor_Desk_CL/hw6`
- **The agent is built** (Problem 3): `agent.py` (entry point), `tools.py` (three tools +
  extraction + pricing + JSON appends), `models.py` (the structured types),
  `prompts/prompt.md` (runtime instructions, with `{{HANDBOOK}}` substituted by
  `agent.py`). Run it:
  `.venv/bin/python agent.py --doc data/practice_docs/p01_bluehen_quote.html`
  — **this spends credits; ask first.** `--show-document` prints what the agent would see
  and exits without calling the model (free).
- **The cache experiment is done** (Problem 4): `cache_test.py` ran all 12 practice
  documents through both setups, 48 model calls, $0.0448. **83.4% saved**; 0 cached tokens
  on all 24 cold calls. Results in `output/cache_test.md` and `output/cache_test.json`.
  **Do not re-run it to verify an edit** — it costs more than everything else here
  combined and takes about an hour. `cache_test.py --dry-run` uses `TestModel` and is free.
- **Self-contradicting documents (fixed 2026-11-04).** `p07` and `p12` state a figure in
  their quote line then revise it in plain prose; the key takes the quote line.
  `prompts/prompt.md` now has **"One document, one set of figures — the quote line wins"**.
  The scoping is load-bearing: `p10`'s subject line is *"Updated mug quote - please ignore
  the earlier one"* and its figures **are** accepted, because it contradicts a *different,
  earlier* document rather than itself. Any future edit to this rule must keep that
  distinction and re-check p07, p12 **and** p10 together. All three verified 6/6 after the
  fix. Note the Problem 4 numbers were measured with the pre-fix prompt and stand as
  measured.
- **96% of an uncached call's cost is cache writes that are never read.** Defeating the
  cache does not buy the $0.10/1M input rate: the provider writes an entry for every new
  prefix and bills the 1.25× premium, so it is really $0.125/1M vs $0.01/1M.
- **The agent is defended** (Problem 6, three layers): code (`tools.py` PDF concealment +
  directive scan), design (`handbook.py` computes the decision; `DEFENDED_TOOLS` withholds
  the traps), prompt (`prompts/prompt.md`). **12/12 practice documents hold, 0 traps, 0
  overrides**, and all four clean quotes still return real values. `output/defense_results.md`
  has the before/after.
- **`output/hw6_report.html` is generated, never edited** (Problem 9). `build_report.py`
  renders it from the eight output JSONs, so no figure on the page is typed in. Re-run any
  experiment, then `.venv/bin/python build_report.py` (free). It must stay **one file with
  no external references, no `<script>`, and no http(s)** — charts are hand-built inline SVG
  and fonts are a system stack. Preview it with the `hw6-report` entry in the workspace
  `.claude/launch.json` (port 8096).
- **`output/exam_results.json` is the graded artefact** (Problem 8): a bare JSON array, one
  object per exam file, exactly 13 fields in the assignment's order. **Written only by
  `exam_run.py` — never hand-edit it**, and never add a key (there is an assertion against
  the field tuple). Provenance lives in `output/exam_run_meta.json`.
  Regenerate: `.venv/bin/python exam_run.py` (spends ~$0.004; `--dry-run` is free).
  10/10 documents, 0 trap calls, 0 unknowns, and the run reproduces byte-identically
  (`exam_results_rerun.json`). Six of the ten exam documents are booby-trapped; all six
  were resisted.
- **`--defenses off` is a real branch, not a flag.** It restores the Problem 3 agent exactly
  (frozen `prompts/prompt_problem3.md`, PDFs uninspected, no directive scan, all three tools,
  model's own decision). Problem 7 needs it — do not let it rot.
  `defense_test.py --config {full,no_code,no_prompt,no_design,none}` switches layers
  independently.
- **Validate `handbook.py` against the key offline after any change to it** — feed it the
  key's figures and expect 12/12. That check is free and is what guarantees a clean quote is
  never refused.
- **Offline tests, free:** `.venv/bin/python tests/test_offline.py` — 92 checks covering
  extraction on all 22 documents, the four concealed payloads, the path guard, both traps, concurrent appends,
  the cost arithmetic, and prompt assembly. Uses `TestModel`. Use these to verify an edit;
  never a live run.
- **Live runs must go through the Terminal panel.** Sandboxed Bash cannot read `.env` (so
  `PORTKEY_API_KEY` is missing) and cannot read certifi's `cacert.pem` (so TLS fails).
  Offline tests and `--show-document` run fine in the sandbox.
- `output/` holds three append-only logs: `trap_calls.json` (seeded `[]`, an entry is a
  finding), `usage_log.json` (tokens + dollars per run), `audit_trail.json` (tool calls +
  final answer). `append_json_list` moves an unparseable file aside rather than
  overwriting it.
- **Six practice documents have been run live** (2026-11-03: p01, p08, p02, p03, p04, p09;
  $0.0038 total). All 36 fields match `practice_key.json`, one tool call each, and
  `trap_calls.json` is still `[]` — the four adversarial documents were resisted. Do not
  re-run them to verify an edit; the logs in `output/` are the evidence. Note `output/`
  therefore carries real run state: `usage_log.json` and `audit_trail.json` each hold six
  entries.
- **Cost reality from the live runs** (a cold start vs. a warm cache): a
  cold run is ~$0.0018, dominated by the one-time cache write; the next run reused 24,149
  of 24,642 input tokens from cache and cost $0.00039. Caching works across separate
  process invocations, so back-to-back runs are far cheaper than the first.
- `submission_spec.json` pairs `agent.py` → `prompts/prompt.md` and lists the outputs built
  so far. Keep it current as each problem names new files, per `AGENTS.md` §4.
- `data (1).zip` and `.DS_Store` are still in this folder. Both are harmless; neither has
  been deleted, and `.gitignore` keeps them out of any repo.
