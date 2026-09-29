"""
costs.py — price every AI call and keep a running total in a CSV ledger
(`costs.csv` next to epitaka.db). One line per call; prints this call / this
run / all time. OpenRouter reports each call's cost itself (`usage.cost`,
USD), which is used as-is. Other models are priced from PRICES; models without
an entry (all Gemini models — free keys) are logged at $0.
"""

import csv
import os
from datetime import datetime, timezone
from pathlib import Path

from . import common_utils as cu

# USD per 1M tokens at PEAK: (cache-hit input, cache-miss input, output).
# Off-peak is half. deepseek-v4-flash is DeepSeek's legacy name for
# deepseek-flash, same price (api-docs.deepseek.com/quick_start/pricing,
# checked 2026-09-29).
PRICES = {
    "deepseek:deepseek-flash":    (0.006, 0.30, 1.20),
    "deepseek:deepseek-v4-flash": (0.006, 0.30, 1.20),
}

LEDGER = Path(cu.EPITAKA_DB).parent / "costs.csv"
_FIELDS = ["time_utc", "model", "label", "cache_hit_tokens",
           "cache_miss_tokens", "output_tokens", "usd"]

_run_total = 0.0
_all_time: float | None = None


def is_peak(t: datetime) -> bool:
    """DeepSeek peak: 01:00-04:00 and 06:00-10:00 UTC, Monday-Friday (Chinese holidays ignored)."""
    return t.weekday() < 5 and (1 <= t.hour < 4 or 6 <= t.hour < 10)


def call_cost(model: str, usage: dict, t: datetime) -> float:
    if "cost" in usage:
        return float(usage["cost"] or 0)
    price = PRICES.get(model)
    if not price:
        return 0.0
    hit, miss, out = price
    usd = (usage.get("prompt_cache_hit_tokens", 0) * hit
           + usage.get("prompt_cache_miss_tokens", 0) * miss
           + usage.get("completion_tokens", 0) * out) / 1_000_000
    return usd if is_peak(t) else usd / 2


def _ledger_total() -> float:
    # Runs inside the AI call's error handling: raising here would turn a
    # good (paid) reply into a retry.
    if not LEDGER.exists():
        return 0.0
    try:
        with open(LEDGER, newline="", encoding="utf-8") as f:
            return sum(float(row["usd"]) for row in csv.DictReader(f))
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"[cost] WARNING: could not read {LEDGER}, all-time total restarts at 0: {e}")
        return 0.0


def record(model: str, label: str, usage: dict, t: datetime | None = None) -> float:
    """Append one ledger line for a finished call and print the running totals."""
    global _run_total, _all_time
    t = t or datetime.now(timezone.utc)
    hit = usage.get("prompt_cache_hit_tokens",
                    (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0))
    # OpenRouter reports prompt_tokens with cached_tokens inside it.
    miss = usage.get("prompt_cache_miss_tokens", usage.get("prompt_tokens", 0) - hit)
    try:
        usd = call_cost(model, usage, t)
    except (TypeError, ValueError) as e:  # never fail an already-paid call over accounting
        print(f"[cost] WARNING: could not price {model} usage {usage!r}: {e}; logging $0")
        usd = 0.0
    if model.startswith("openrouter:") and "cost" not in usage:
        print(f"[cost] WARNING: OpenRouter sent no cost for {model}; logging $0")
    if _all_time is None:
        _all_time = _ledger_total()
    _run_total += usd
    _all_time += usd

    # A ledger write failure must not fail the (already paid-for) call.
    try:
        new_file = not LEDGER.exists()
        os.makedirs(LEDGER.parent, exist_ok=True)
        with open(LEDGER, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(_FIELDS)
            w.writerow([t.strftime("%Y-%m-%d %H:%M:%S"), model, label,
                        hit, miss,
                        usage.get("completion_tokens", 0), f"{usd:.6f}"])
    except OSError as e:
        print(f"[cost] WARNING: could not write {LEDGER}: {e}")

    print(f"[cost] {model} ${usd:.4f} this call, ${_run_total:.4f} this run, "
          f"${_all_time:.4f} all time")
    return usd
