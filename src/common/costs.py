"""
costs.py — price every AI call and keep a running total in a CSV ledger
(`costs.csv` next to epitaka.db). One line per call; prints this call / this
run / all time. OpenRouter reports each call's cost itself (`usage.cost`,
USD), which is used as-is. DeepSeek is priced from PRICES and Gemini from
_gemini_price; a model without a price is logged at $0 with a warning.
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

# Gemini, standard paid tier, USD per 1M tokens: (cached input, input, output
# including thinking). From ai.google.dev/gemini-api/docs/pricing, page dated
# 2026-09-24, checked 2026-09-30. Only models read off that page are priced.
_FLASH_2026 = (0.075, 0.75, 3.75)
_FLASH_2027 = (0.15, 1.50, 7.50)
_FLASH_PRICE_CHANGE = datetime(2027, 1, 1, tzinfo=timezone.utc)
_PRO_UP_TO_200K = (0.20, 2.00, 12.00)
_PRO_OVER_200K = (0.40, 4.00, 18.00)

LEDGER = Path(cu.EPITAKA_DB).parent / "costs.csv"
_FIELDS = ["time_utc", "model", "label", "cache_hit_tokens",
           "cache_miss_tokens", "output_tokens", "usd",
           "lines", "status", "seconds", "api_usd", "detail"]

_run_total = 0.0
_all_time: float | None = None


def is_peak(t: datetime) -> bool:
    """DeepSeek peak: 01:00-04:00 and 06:00-10:00 UTC, Monday-Friday (Chinese holidays ignored)."""
    return t.weekday() < 5 and (1 <= t.hour < 4 or 6 <= t.hour < 10)


def _gemini_price(model: str, prompt_tokens: int, t: datetime) -> tuple[float, float, float] | None:
    if model in ("gemini-3.8-flash", "gemini-3.7-flash"):
        return _FLASH_2026 if t < _FLASH_PRICE_CHANGE else _FLASH_2027
    if model == "gemini-3.1-pro-preview":
        return _PRO_UP_TO_200K if prompt_tokens <= 200_000 else _PRO_OVER_200K
    return None


def call_cost(model: str, usage: dict, t: datetime) -> float:
    if "cost" in usage:
        return float(usage["cost"] or 0)
    hit_tokens = usage.get("prompt_cache_hit_tokens", 0)
    miss_tokens = usage.get("prompt_cache_miss_tokens", 0)
    gemini = _gemini_price(model, hit_tokens + miss_tokens, t)
    if gemini:
        hit, miss, out = gemini
        # No off-peak discount: that is DeepSeek's.
        return (hit_tokens * hit + miss_tokens * miss
                + usage.get("completion_tokens", 0) * out) / 1_000_000
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


def _upgrade_ledger() -> None:
    """Add the newer columns to a ledger written before they existed, leaving them blank."""
    with open(LEDGER, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows or rows[0] != _FIELDS[:len(rows[0])]:
        return  # not an older copy of our own header: leave it alone
    pad = [""] * (len(_FIELDS) - len(rows[0]))
    tmp = LEDGER.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(_FIELDS)
        w.writerows(row + pad for row in rows[1:])
    os.replace(tmp, LEDGER)


def record(model: str, label: str, usage: dict, t: datetime | None = None, *,
           lines: int = 0, status: str = "ok", seconds: float = 0.0,
           detail: str = "") -> float:
    """
    Append one ledger line for a call attempt and print the running totals.

    `lines` is how many sentences the call carried, `status` is ok / limit /
    error / timeout, `seconds` is the wall time of the call, `detail` is the
    error text (a Claude limit message names its reset time there). `usd` is
    what the call cost at this model's own price; Claude's subscription has
    none, so its API-rate value comes from usage["api_usd"] into `api_usd`.
    """
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
    if model.startswith("gemini-") and _gemini_price(model, 0, t) is None:
        print(f"[cost] WARNING: no price known for {model}; logging $0")
    if _all_time is None:
        _all_time = _ledger_total()
    _run_total += usd
    _all_time += usd

    # A ledger write failure must not fail the (already paid-for) call.
    # A model with a price already has its API-rate value in `usd`. Claude has
    # none of its own, so a missing figure stays blank: unknown, not a real $0.
    api_usd = usage.get("api_usd")
    if api_usd is None and not model.startswith("claude:"):
        api_usd = usd

    try:
        new_file = not LEDGER.exists()
        os.makedirs(LEDGER.parent, exist_ok=True)
        if not new_file:
            with open(LEDGER, encoding="utf-8") as f:
                if f.readline().rstrip("\r\n").split(",") != _FIELDS:
                    _upgrade_ledger()
        with open(LEDGER, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(_FIELDS)
            w.writerow([t.strftime("%Y-%m-%d %H:%M:%S"), model, label,
                        hit, miss,
                        usage.get("completion_tokens", 0), f"{usd:.6f}",
                        lines, status, f"{seconds:.1f}",
                        "" if api_usd is None else f"{api_usd:.6f}",
                        " ".join(str(detail).split())[:200]])
    except OSError as e:
        print(f"[cost] WARNING: could not write {LEDGER}: {e}")

    tag = "" if status == "ok" else f" [{status}]"
    print(f"[cost] {model}{tag} ${usd:.4f} this call, ${_run_total:.4f} this run, "
          f"${_all_time:.4f} all time")
    return usd
