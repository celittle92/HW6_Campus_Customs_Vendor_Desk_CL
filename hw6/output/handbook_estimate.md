# What the handbook costs us

`data/shop_handbook.md` is the Campus Customs staff handbook. The vendor desk agent will
send it to the model on **every single call**, so its size is a recurring charge, not a
one-off. This file measures it and prices it.

---

## 1. The token count

**The handbook is 10,058 tokens.**

| Measure | Value |
|---|---|
| Tokens | **10,058** |
| Characters | 28,903 |
| Words | 6,127 |
| Lines | 339 |
| Bytes on disk | 29,241 |
| Density | 2.87 characters per token |

### How I got it

I counted with a real tokenizer rather than estimating, because this number feeds every
dollar figure below:

```bash
cd hw6
.venv/bin/python count_tokens.py data/shop_handbook.md --calls 1000
```

[`count_tokens.py`](../count_tokens.py) reads the file, encodes it with OpenAI's
**`tiktoken`** library, and counts the resulting tokens. It makes no model call and costs
nothing. The same script also produces the cost table in §2, so the arithmetic below is
not done by hand.

### Three caveats, in order of how much they matter

**1. The encoding is a stand-in.** `tiktoken` has no table for `gpt-6-luna`, so I used
`o200k_base` — the encoding OpenAI's current GPT-4o and GPT-5-generation models use, and
the closest published match. To show how much that choice moves the number, I ran the
older `cl100k_base` encoding as a cross-check:

| Encoding | Tokens | Difference |
|---|---|---|
| `o200k_base` (used) | 10,058 | — |
| `cl100k_base` | 10,184 | +126 (+1.3%) |

A 1.3% spread. Whichever encoding `gpt-6-luna` actually uses, the estimate is sound to
roughly the nearest hundred tokens, which is far tighter than the decisions it informs.

**2. Line endings cost 11 tokens.** The file is saved with Windows CRLF line endings. Read
normally in Python, those become plain newlines and the count is 10,058; sent byte-for-byte
with the carriage returns intact it is 10,069. The 0.1% difference is noted for
completeness and ignored everywhere below. (It also explains why the file is 29,241 bytes
but 28,903 characters — 338 carriage returns.)

**3. This prices the handbook alone.** A real call also carries the system prompt, the
vendor document being read, and the model's answer. Those are costed when they exist. The
handbook is the part that is identical on every call, which is exactly why it is worth
measuring on its own.

### Where the bulk of it is

Section tokens add up to the 10,058 total exactly:

| § | Section | Tokens | Share |
|---|---|---:|---:|
| 9 | **Product catalogue** (177 SKUs) | **6,920** | **68.8%** |
| 10 | **Recent purchase orders** (40 POs) | **1,462** | **14.5%** |
| 5 | Approved vendors | 417 | 4.1% |
| 4 | Purchasing rules | 269 | 2.7% |
| 1 | Who we are | 192 | 1.9% |
| 12 | Big-weekend planning | 123 | 1.2% |
| 6 | Removed and pending vendors | 117 | 1.2% |
| 2 | Staff and roles | 106 | 1.1% |
| 11 | Brand and quality checklist | 105 | 1.0% |
| 7 | Returns and exchanges | 95 | 0.9% |
| 8 | Discounts | 94 | 0.9% |
| 13 | How the vendor desk agent should report | 71 | 0.7% |
| 3 | Store hours | 63 | 0.6% |
| — | Title and preamble | 24 | 0.2% |
| | **Total** | **10,058** | **100%** |

**Two tables are 83% of the cost.** The catalogue and the purchase-order history together
are 8,382 of the 10,058 tokens. Everything that actually states a *rule* — sections 4, 5, 6
and 13, the four purchasing checks, the vendor lists, and the required report format — comes
to 874 tokens, under 9% of the file. Worth remembering for Problem 4.

---

## 2. What it costs

### The price list

From `data/prices.json`, for `gpt-6-luna`, per 1M tokens:

| Rate | Per 1M tokens | Per single token |
|---|---:|---:|
| Input (uncached) | $0.10 | $0.0000001 |
| Cached input | $0.01 | $0.00000001 |
| Cache write | $0.125 | $0.000000125 |
| Output | $0.50 | $0.0000005 |

The output rate is listed for completeness but is **not used below**. The handbook is
something we send, never something the model writes back, so it is an input-side cost only.

Cached input is **10× cheaper** than uncached. A cache write costs **1.25×** a normal input
token — you pay a small premium once to store the prompt, then read it cheaply thereafter.

### The formula

```
cost = tokens ÷ 1,000,000 × rate_per_1M
```

With the handbook at 10,058 tokens, `10,058 ÷ 1,000,000 = 0.010058` million tokens. Every
figure below is that 0.010058 multiplied by a rate.

### One call

**Uncached** — the whole handbook charged at the full input rate:

```
0.010058 million × $0.10 per million = $0.0010058
```

**= $0.001006, about a tenth of one cent.**

**Cached** — two different numbers, depending on whether this is the call that *writes* the
cache or one that *reads* it:

```
cache write (first call):   0.010058 million × $0.125 per million = $0.00125725
cached read (later calls):  0.010058 million × $0.01  per million = $0.00010058
```

**= $0.001257 to write it, $0.000101 to read it.**

So the first cached call is slightly *more* expensive than an uncached one ($0.001257 vs
$0.001006 — the 1.25× premium), and every call after it is 10× cheaper.

### 1,000 calls

**Uncached** — every call pays full price:

```
1,000 × $0.0010058 = $1.0058
```

**= $1.01.**

**Cached** — call 1 writes the cache, calls 2 through 1,000 read it:

```
call 1          :      1 × $0.00125725 = $0.00125725
calls 2–1,000   :    999 × $0.00010058 = $0.10047942
                                         ___________
total           :                        $0.10173667
```

**= $0.1017, about ten cents.**

### Side by side

| | 1 call | 1,000 calls |
|---|---:|---:|
| **Uncached** | $0.001006 | **$1.0058** |
| **Cached** | $0.001257 (write) / $0.000101 (read) | **$0.1017** |
| **Saving** | — | **$0.9041 (89.9%)** |

### When caching starts paying

The cache write costs $0.00125725 against an uncached call's $0.0010058, so you are
$0.00025145 behind after the first call — and each later call saves $0.00090522. Setting
the two totals equal:

```
0.00125725 + 0.00010058 × (n − 1)  =  0.0010058 × n
                            n  =  1.28
```

**Caching is already cheaper by the second call.** There is no volume threshold to reach
and no reason not to use it.

---

## 3. Two honest limits on the $0.1017 figure

**Caches expire.** That number assumes one cache write serving 999 reads, which only holds
if the calls arrive close enough together to keep the cache warm. OpenAI's prompt cache
typically drops after a few minutes idle. If the handbook has to be re-written *m* times
across 1,000 calls:

| Cache writes in 1,000 calls | Cost | vs uncached |
|---:|---:|---:|
| 1 (perfect) | $0.1017 | 10.1% |
| 10 | $0.1121 | 11.1% |
| 100 | $0.2162 | 21.5% |

Even at 100 rewrites — a cold cache every tenth call — caching still costs a fifth of the
uncached price. **The conclusion holds comfortably even if the cache performs badly.**

**Caching needs a stable prefix.** The cached portion has to be byte-identical from call to
call, so the handbook must sit at the *front* of the prompt with the per-document text
*after* it. Put the vendor quote first and nothing caches at all.

---

## 4. What this means for HW6

The data pack is 22 documents — 12 practice and 10 exam. At one call per document:

| Run | Uncached | Cached | Math |
|---|---:|---:|---|
| Practice set (12 docs) | $0.0121 | $0.0024 | `12 × $0.0010058` / `$0.00125725 + 11 × $0.00010058` |
| Exam set (10 docs) | $0.0101 | $0.0022 | `10 × $0.0010058` / `$0.00125725 + 9 × $0.00010058` |
| **Both (22 docs)** | **$0.0221** | **$0.0034** | `22 × $0.0010058` / `$0.00125725 + 21 × $0.00010058` |

**A full pass over every document in the data pack costs about two cents of handbook,
uncached.** The handbook is not what makes this assignment expensive — a complete run is
cents, not dollars. Repeated development runs are what add up, and a 90% discount on the
largest fixed part of every prompt is worth having.

If cost ever does need to come down further, §1's section table says where to look: the
177-SKU catalogue is 69% of the handbook, and a single vendor quote names exactly one SKU.

---

*Counted and priced on 2026-11-03 with [`../count_tokens.py`](../count_tokens.py) against
`data/prices.json` (OpenAI Standard pricing per 1M tokens, MGT 409 Lecture 11). Reproduce
with `.venv/bin/python count_tokens.py data/shop_handbook.md --calls 1000`. No model call
was made; nothing was spent producing this file.*
