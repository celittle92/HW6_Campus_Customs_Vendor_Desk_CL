#!/usr/bin/env python3
"""Count the tokens in a document and price them against the gpt-6-luna list.

Deterministic measurement, no model call and no network: this is plumbing, not an AI
step, so it is excluded from the "every script must call a model" rule in AGENTS.md.
Counting with a tokenizer rather than asking a model is also the point — a model's own
estimate of its token count is a guess, and this number feeds the cost estimates.

Takes the document path as an argument rather than defaulting to one, so the file being
measured is always visible in the command that produced a number.

Usage, from hw6/:
    .venv/bin/python count_tokens.py data/shop_handbook.md
    .venv/bin/python count_tokens.py data/shop_handbook.md --calls 1000 --json

The encoding is a stand-in: tiktoken has no table for gpt-6-luna, so this uses
o200k_base, the encoding OpenAI's current GPT-4o/GPT-5-generation models use. Pass
--encoding to compare against another one.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Keep tiktoken's downloaded encoding table inside the project, so a count is
# reproducible from a cold machine and does not depend on a temp directory that
# differs between shells. The first run needs network; every run after it is offline.
os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(HERE / ".tiktoken_cache"))

import tiktoken  # noqa: E402  (after TIKTOKEN_CACHE_DIR is set)

from app_config import REQUIRED_OPENAI_MODEL  # noqa: E402
from tools import PRICES_PATH, load_rates, price  # noqa: E402

DEFAULT_ENCODING = "o200k_base"
DEFAULT_MODEL = REQUIRED_OPENAI_MODEL


def count_tokens(text: str, encoding_name: str) -> int:
    return len(tiktoken.get_encoding(encoding_name).encode(text))


def estimate(tokens: int, rates: dict[str, float], calls: int) -> dict[str, float]:
    """Input-side cost of resending `tokens` on every one of `calls` calls.

    Two scenarios, both input-only — output tokens are the answer's, not the
    handbook's, so they are deliberately not counted here.

      uncached: every call pays the full input rate.
      cached:   the first call writes the cache, the remaining calls read it.
    """
    one_uncached = price(tokens, rates["input_per_1m"])
    one_cache_write = price(tokens, rates["cache_write_per_1m"])
    one_cached_read = price(tokens, rates["cached_input_per_1m"])
    return {
        "one_call_uncached": one_uncached,
        "one_call_cache_write": one_cache_write,
        "one_call_cached_read": one_cached_read,
        "n_calls_uncached": one_uncached * calls,
        "n_calls_cached": one_cache_write + one_cached_read * (calls - 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("document", type=Path, help="the file to measure")
    ap.add_argument("--encoding", default=DEFAULT_ENCODING)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--prices", type=Path, default=PRICES_PATH)
    ap.add_argument("--calls", type=int, default=1000, help="how many calls resend the document")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    text = args.document.read_text(encoding="utf-8")
    tokens = count_tokens(text, args.encoding)
    rates = load_rates(args.prices, args.model)
    costs = estimate(tokens, rates, args.calls)

    payload = {
        "document": str(args.document),
        "characters": len(text),
        "words": len(text.split()),
        "lines": text.count("\n") + 1,
        "tokens": tokens,
        "encoding": args.encoding,
        "chars_per_token": round(len(text) / tokens, 3),
        "model": args.model,
        "rates_per_1m": rates,
        "calls": args.calls,
        "costs_usd": {k: round(v, 8) for k, v in costs.items()},
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return

    n = args.calls
    print(f"{args.document}")
    print(f"  characters {payload['characters']:,}   words {payload['words']:,}   lines {payload['lines']:,}")
    print(f"  tokens     {tokens:,}  ({args.encoding}, {payload['chars_per_token']} chars/token)")
    print()
    print(f"{args.model} input-side cost of resending this document")
    print(f"  rates/1M: input ${rates['input_per_1m']}  cached ${rates['cached_input_per_1m']}  cache write ${rates['cache_write_per_1m']}")
    print(f"  1 call,  uncached          ${costs['one_call_uncached']:.6f}")
    print(f"  1 call,  cache write       ${costs['one_call_cache_write']:.6f}")
    print(f"  1 call,  cached read       ${costs['one_call_cached_read']:.6f}")
    print(f"  {n:,} calls, uncached      ${costs['n_calls_uncached']:.4f}")
    print(f"  {n:,} calls, cached        ${costs['n_calls_cached']:.4f}")
    saved = costs["n_calls_uncached"] - costs["n_calls_cached"]
    print(f"  saved by caching           ${saved:.4f}  ({saved / costs['n_calls_uncached']:.1%})")


if __name__ == "__main__":
    main()
