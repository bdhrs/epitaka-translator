# Spec — Model-selectable verification (drop B.AI from verify_translation)

## Overview
`src/verify_translation.py` reviews already-published translations against
the Pāli source and its linked texts, saving findings to
`translation_remarks` (and, with `--apply`, overwriting
`sentences.translation`). It is currently hardwired to the B.AI gateway
(`common/ai_client_bai.py`, model `deepseek-v4-flash`, one key, no model
choice). This thread removes the B.AI path from the verifier and routes it
through the main provider stack (`common/ai_client.py`), so a review can run
on any configured model — `claude:sonnet`, `deepseek:deepseek-flash`,
`azure:DeepSeek-V4.1-Flash`, OpenRouter, Gemini — with the same key
rotation, 429 parking, model fallback and cost logging the translator has.
It also adds a `just` recipe that reviews the Kannada corpus with Claude
Sonnet on the Claude Pro subscription.

## What it should do
1. **`--model` flag** on `verify_translation.py`: single model or
   comma-separated ordered list (first preferred; `ai_client.ModelPool`
   drops a model after every key is 429-parked on it and falls to the next).
   Bare names are Gemini models; `provider:model` spelling exactly as in
   `book_translator.py` (`deepseek:deepseek-flash` — never versioned;
   `azure:DeepSeek-V4.1-Flash` stays as is).
2. **Default when omitted**: the same fallback chain as
   `book_translator.FALLBACK_MODEL_CHAIN` (defined locally in the verify
   script; `book_translator` is not imported — it is heavy and runs
   `load_dotenv()` into real keys).
3. **Rotator from env only**: `ai_client.make_rotator([])` builds the
   key pool from `GEMINI|DEEPSEEK|OPENROUTER|AZURE|CLAUDE_KEY_<N>` env
   vars (`CLAUDE_KEY_1` only marks the provider as wanted — no real key
   needed). No `--api-keys` flag (cut in review: a layer nobody asked
   for).
4. **`load_dotenv()` inside `main()`**, NOT at module import — the tests
   import this module, and a top-level `load_dotenv()` (the
   `study_builder.py` pattern) would load the real `.env` keys into every
   test run.
5. **Off-peak gate**: a run pinned to a `deepseek:` model sleeps through
   DeepSeek's peak hours (01:00–04:00 and 06:00–10:00 UTC, Mon–Fri, Chinese
   holidays included), checked **right before each AI request** — same
   placement rule as `book_translator._handle_chunk` (user, 2026-10-20) —
   using `common/costs.py`'s `is_peak`/`off_peak_start`, never importing
   `book_translator`. `--dry-run` never waits. Azure/Claude/Gemini never wait.
   **Stated limitation (review finding):** the gate checks only
   `models[0]` — the model the pool starts on. A mid-run fallback onto a
   `deepseek:` model during peak hours pays double with no wait; the
   verify script cannot see the pool switch. Pin a single `deepseek:`
   model when reviewing at peak times, or accept the price.
6. **B.AI-specific flags removed**: `--max-tokens`,
   `--thinking-budget-tokens` (B.AI reasoning-budget concept). The
   `ai_client` path needs neither.
7. Everything else unchanged: chunking, prompts, `--apply` semantics,
   `--dry-run` (works with **zero keys configured**), `--limit`, log dir
   (now written by `ai_client.call_ai_with_logging` in its timestamped
   prompt/response format), JSON parsing via
   `ai_client.parse_ai_json_response(raw, ("remarks",))`. One deliberate
   change (user choice, review round 3): each saved remark's `note` column
   now carries its severity ("wrong"/"critical") so findings stay
   filterable — this makes the module header's old promise true.
8. **Claude limit behaviour (review finding):** when the subscription
   limit exhausts a single-model pool, `ai_client` exits loudly — it
   prints `[RESET-AT] <epoch>`, sends the Telegram alert and
   `sys.exit(1)` (verified in `_fatal_all_keys_exhausted`, ai_client.py
   621-632). The run does NOT skip the rest of the corpus. But there is
   no runner to auto-resume: re-run the same command after the window.
   Separately, a chunk that fails for a NON-429 reason (timeout, unparseable
   reply) is skipped and the run continues — skipped chunks are visible
   in the log as `AI call failed ... Skipping` lines.
9. **Re-runs duplicate remarks (review finding, verified):**
   `RemarkWriter.save` is a plain INSERT with no dedupe, so a second pass
   over the same book adds duplicate `translation_remarks` rows. Accepted
   for now; the live probe and any re-run must therefore snapshot the lang
   DB first (`sqlite3 .backup`, the same rule `just pull` follows).
10. **Justfile recipes**, matching the sibling relay recipes (background,
    logged — a full-corpus Claude review outlives a terminal):
    `review lang="kn" model="claude:sonnet" *flags:` →
    `nohup uv run src/verify_translation.py --lang {{lang}} --model {{model}} {{flags}} >> data/review_{{lang}}.log 2>&1 &`
    plus a tail hint, and `review-kn-claude` / `review-kn-azure` shortcuts
    (user-requested follow-up). Report-only by default; `--apply` stays a
    manual, explicit decision.
11. **Stoppable background runs (review round 4, MEDIUM finding):**
    `just stop` must also stop review runs. The existing recipe kills
    runner.sh / book_translator.py / a claude -p child, but nothing matched
    `verify_translation.py`, so a background `just review` had no stop.
    Fix: `just stop` gains `-pkill -f "[v]erify_translation.py --lang
    {{lang}} "`. A claude -p child of a review call is one-shot (prompt on
    stdin) and exits on its own after its parent dies — no extra pattern
    needed. Checked while fixing: the existing claude pattern's
    `TARGET LANGUAGE:` clause cannot match anything, because
    ai_claude_code passes the prompt via stdin, not the command line
    (NOTICED — NOT TOUCHING: translator-owned line, out of scope).
12. **note-column semantics (review round 4, LOW finding, resolved):**
    verify remarks carry severity in `note`, exactly like the glossary
    pipeline already does (glossary_builder.py INSERTs severity into the
    same column); nothing in src/ or the exports READS the column — both
    pipelines are writers only. Consistent, no change needed.

## Assumptions & uncertainties
- `ai_client_bai.py` itself is **not touched** — tech.md pins it as a third
  provider with its own names. Only `verify_translation.py`'s import of it
  goes away. (Verified: no other script imports it; `study_builder`'s
  import is commented out.)
- The review prompt sizes (~4k context + line pairs) are far below every
  provider's limit, so no per-provider prompt shrinking is needed.
- Verified facts: provider dispatch in `ai_client._generate_with_retry`
  routes `claude:` to the Claude Code CLI (subscription billing, strips
  `ANTHROPIC_API_KEY`), others to `ai_openai_compat`; `make_rotator` picks
  up `CLAUDE_KEY_<N>`; `call_ai_with_logging` writes prompt/response logs;
  `parse_ai_json_response` exists in `ai_client` with the same shape.
- Assumed: `.env` already holds `CLAUDE_KEY_1` (the translator's `just
  relay` uses `claude:sonnet` today).

## Constraints
- uv only (`uv run src/verify_translation.py`); no pip path.
- `.env` is never committed or agent-edited; no new env vars are introduced,
  so `.env.example` is unchanged.
- Tests must delete every `*_KEY_*` env var and fake the network — a stray
  call spends paid keys. Suite runs as `timeout 60 uv run pytest -q`
  (tests stub `time.sleep`).
- Direct DeepSeek stays `deepseek:deepseek-flash`, version-free.
- Pyright must stay at 0 errors: `cd <repo> &&
  /home/bodhirasa/MyFiles/3_Active/dpd-db/.venv/bin/pyright src tests`.

## How we'll know it's done
- `uv run src/verify_translation.py --lang kn --dry-run` prints the model
  pool and a prompt, calls nothing, and importing the module does not
  load `.env` keys into the test environment.
- New pytest coverage: model parsing/default routing through `ai_client`
  (network faked), off-peak gate waits before a `deepseek:` call and never
  for others, import-time key safety, justfile pins `review` →
  `claude:sonnet` in its background form (same style as
  `test_deepseek_model_name.py`), and no `ai_client_bai` import remains in
  `verify_translation.py`.
- Pyright 0 errors; full suite passes under `timeout 60`.
- A short live probe (`--book <small book> --limit 1`, report-only, after
  an `sqlite3 .backup` snapshot of the lang DB) on Claude produces remarks
  rows without touching translations.

## What's not included
- No changes to `ai_client_bai.py`, `glossary_builder.py`, `runner.sh`, or
  the translation path.
- No changes to the Telegram alert or runner.sh auto-resume machinery for
  review runs: a limit-hit review exits with the alert and is re-run by
  hand after the window (the background `review` recipe only logs, it
  does not restart).
- No new providers, no changes to `--apply` safety semantics.
- No review of glossary pairs (separate pipeline in `glossary_builder.py`).
