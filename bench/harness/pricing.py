"""Estimated cost from token counts at Anthropic list prices. Estimates, not invoices: they ignore discounts,
batch pricing and any price change after PRICES_AS_OF. An unknown model is an error, not a silent default."""

from __future__ import annotations

PRICES_AS_OF = "2026-10-06"
PRICES: dict[
    str, tuple[float, float, float, float]
] = {  # $/MTok: input, output, cache write (1.25x), cache read
    "claude-sonnet-5-5": (2.0, 10.0, 2.5, 0.20),
    "claude-opus-5-5": (4.0, 20.0, 5.0, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.125, 0.01),
}


def require_priced(model: str) -> None:
    if model not in PRICES:
        raise ValueError(
            f"no list price for {model!r}; add it to bench/harness/pricing.py with its source date"
        )


def estimated_cost(model: str, usage: dict[str, int]) -> float:
    require_priced(model)
    p_in, p_out, p_cw, p_cr = PRICES[model]
    return (
        usage["input_tokens"] * p_in
        + usage["output_tokens"] * p_out
        + usage["cache_write_tokens"] * p_cw
        + usage["cache_read_tokens"] * p_cr
    ) / 1e6


__all__ = ["PRICES", "PRICES_AS_OF", "estimated_cost", "require_priced"]
