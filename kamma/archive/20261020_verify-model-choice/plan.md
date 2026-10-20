# Plan — Model-selectable verification (drop B.AI from verify_translation)

Spec: `kamma/threads/20261020_verify-model-choice/spec.md`

## Architecture Decisions
- `verify_translation.py` keeps owning chunking, prompts and the
  save/apply flow. All AI calling goes through
  `common/ai_client.call_ai_with_logging` (rotator + ModelPool fallback +
  cost ledger + prompt/response logs), replacing `ai_client_bai` entirely
  in this script. `ai_client_bai.py` itself is untouched (tech.md pins it
  as a separate provider).
- The fallback model chain is defined **locally** in verify as a copy of
  `book_translator.FALLBACK_MODEL_CHAIN`. `book_translator` is never
  imported: it is heavy, wires config/database stubs, and its import runs
  `load_dotenv()` into the real keys.
- The DeepSeek off-peak gate is implemented locally against
  `common/costs.py` (`is_peak`, `off_peak_start`), checked **right before
  each AI request** inside `process_chunk` — same placement rule as
  `book_translator._handle_chunk` (user, 2026-10-20). `wait_for_off_peak`
  is not imported from `book_translator` (same heaviness reason).
- Model selection is a small pure function `resolve_models(arg)` so tests
  can pin parsing/default behaviour without touching the network.
- `load_dotenv()` is called inside `main()`, never at module import —
  tests import this module and must not inherit the real `.env` keys
  (review finding).
- The `just review` recipe matches the sibling relay recipes: background
  `nohup` + log + tail hint, variadic `*flags` so `--dry-run`, `--limit`,
  `--book` pass through (review findings 2 and 3).
- No new env vars, no `.env.example` change, no `runner.sh` change.
- Known limitations accepted as-is (review findings 4, 5, 6): the
  off-peak gate covers only `models[0]`; a Claude-limit exit must be
  re-run by hand (it exits loudly via `_fatal_all_keys_exhausted`, it
  does not skip the corpus); `RemarkWriter` has no dedupe, so re-runs
  duplicate remark rows — snapshot the lang DB before a run that writes.

---

## Phase 1 — Rewire verify_translation.py to the ai_client stack

- [x] 1.1 Write the dated tech.md note BEFORE the code: verify_translation
  now runs on the `ai_client` provider stack (`--model` flag, default =
  the translator's fallback chain); `ai_client_bai` is no longer used by
  verify (the module itself stays); the DeepSeek off-peak gate applies to
  `deepseek:` models in review runs too.
  → verify: `rg -n "verify" kamma/tech.md` shows the dated note.

- [x] 1.2 Imports and startup: add `from dotenv import load_dotenv` at
  the top but call `load_dotenv()` **inside `main()`** right before
  `make_rotator` — never at import time (tests import this module);
  replace the `ai_client_bai` import with `from common import ai_client
  as ai` in BOTH import branches (package and script fallback); delete
  the B.AI-flavoured constants (`DEFAULT_MAX_TOKENS`,
  `DEFAULT_THINKING_BUDGET_TOKENS`); add
  `DEFAULT_MODELS = [...copy of book_translator.FALLBACK_MODEL_CHAIN...]`.
  → verify: `rg -n "ai_client_bai|B.AI|bai" src/verify_translation.py`
  returns nothing; pyright on the file is clean.

- [x] 1.3 Argparse: add `--model` (default `""` → `DEFAULT_MODELS`; accepts
  a comma-separated ordered list); remove `--max-tokens` and
  `--thinking-budget-tokens` — and do NOT add `--api-keys` (cut in
  review); update the module docstring's usage examples (drop the B.AI
  wording, add `--model claude:sonnet`); print the resolved model pool
  like book_translator does (`[model] Using model pool: ...`).
  → verify: `uv run src/verify_translation.py --help` shows the new flags
  and no B.AI flags.

- [x] 1.4 Call path: in `main()`, `load_dotenv()` then
  `rotator = ai.make_rotator([])` (env keys only — no `--api-keys` flag);
  add pure helper `resolve_models(arg: str) -> list[str]` (split on
  comma, strip; empty → copy of `DEFAULT_MODELS`); thread `rotator` and
  `models` through `process_book` → `process_chunk`; in `process_chunk`
  replace the `ai.call_ai_with_logging(...)` B.AI call with the
  ai_client signature (`rotator=`, `prompt=`, `book_id=`, `chunk_id=`,
  `log_dir=`, `model=models[0]`, `models=models`, `system_prompt=`) and
  parse with `ai.parse_ai_json_response(raw, ("remarks",))`. Update
  `process_chunk`'s signature/kwargs accordingly (drop `max_tokens`,
  `thinking_budget_tokens`).
  → verify: pyright 0 errors on src.

- [x] 1.5 Off-peak gate: local `_wait_for_off_peak(model: str) -> bool`
  in verify using `common.costs.is_peak` / `off_peak_start`, sleeping in
  ≤300s slices (flush-printed `[PEAK]` line, mirroring
  book_translator lines 1027–1051); called in `process_chunk` **right
  before** the AI call, only when `models[0]` starts with `deepseek:`
  (stated limitation, review finding 4: a mid-run fallback onto a
  deepseek model is not gated — the script cannot see the pool switch;
  documented in `--model` help); `--dry-run` never reaches it (it
  returns before).
  → verify: `uv run src/verify_translation.py --lang kn --dry-run
  --model claude:sonnet --book <small-kn-book> --limit 1` prints the model
  pool and a prompt and makes no call (no new files in the log dir).

## Phase 2 — Justfile recipe

- [x] 2.1 Add to justfile next to the relay recipes, matching their
  background pattern (review finding 3) and variadic for extra flags
  (review finding 2):
  `review lang="kn" model="claude:sonnet" *flags:` →
  `nohup uv run src/verify_translation.py --lang {{lang}} --model {{model}} {{flags}} >> data/review_{{lang}}.log 2>&1 &`
  plus an `@echo` tail hint (`just tail-review {{lang}}` or plain
  `tail -f`), with a one-line comment ("report-only by default; pass
  `--apply` yourself; snapshot the lang DB before a re-run over the same
  book — remarks are not deduped").
  → verify: `just --dry-run review kn claude:sonnet --limit 1` prints the
  exact command without executing it (just's own dry-run, since the
  recipe's own `--dry-run` flag would collide); `just --list` shows
  `review`.

## Phase 3 — Tests (network faked, keys deleted)

- [x] 3.1 `tests/test_verify_model_choice.py::test_resolve_models`: single
  model, comma list with spaces, and empty → `DEFAULT_MODELS` copy (not
  the same list object).
  → verify: `timeout 60 uv run pytest -q tests/test_verify_model_choice.py`
  passes.

- [x] 3.2 Routing test: with every `*_KEY_*` env var deleted
  (pattern of `tests/test_mula_pause.py` line 110) and
  `ai.call_ai_with_logging` monkeypatched to capture kwargs, run
  `process_chunk` on a tiny temp DB and assert the call went out with the
  chosen `model`/`models` and system prompt, and that a canned
  `{"remarks": [...]}` is saved to `translation_remarks` (temp DB).
  → verify: same pytest run; no network, no real keys in the test env.

- [x] 3.3 Off-peak test (pattern of `tests/test_off_peak.py`'s Clock):
  `_wait_for_off_peak("deepseek:deepseek-flash")` sleeps when
  `costs.is_peak` is monkeypatched True and returns without sleeping for
  `"claude:sonnet"` / `"azure:DeepSeek-V4.1-Flash"` / off-peak times;
  `time.sleep` stubbed.
  → verify: same pytest run under `timeout 60`.

- [x] 3.4 Pin tests (style of `tests/test_deepseek_model_name.py`): the
  justfile contains a `review` recipe whose default model is
  `claude:sonnet` and whose command is a background `nohup` with the
  `*flags` passthrough; `src/verify_translation.py` contains no
  `ai_client_bai` import.
  → verify: same pytest run.

- [x] 3.5 Import-safety test (review finding 1): with
  `dotenv.load_dotenv` monkeypatched to record calls, import (or
  `importlib.reload`) `verify_translation` and assert it was NOT called
  at import time — only `main()` may load `.env`.
  → verify: same pytest run.

- [x] 3.6 Full suite + type check: `timeout 60 uv run pytest -q` all pass;
  `cd /home/bodhirasa/MyFiles/3_Active/epitaka-translator &&
  /home/bodhirasa/MyFiles/3_Active/dpd-db/.venv/bin/pyright src tests`
  reports 0 errors.
  → verify: paste both outputs into this plan.

## Phase 4 — Live probe (report-only, paid/subscription quota)

- [x] 4.0 Snapshot first (review finding 6): `sqlite3 data/epitaka_kn.db
  ".backup 'data/epitaka_kn_pre_review_<date>.db'"` — the probe writes
  real `translation_remarks` rows and `RemarkWriter` has no dedupe.
  → verify: the snapshot file exists and opens.

- [~] 4.1 Dry-run first  # dry-run half verified; live Claude probe deferred (no local CLAUDE_KEY_1), then `uv run src/verify_translation.py --lang kn
  --model claude:sonnet --book <smallest translated kn book> --limit 1`:
  confirm a `[AI] calling:` line, a prompt/response pair in the log dir,
  and (if anything flagged) new `translation_remarks` rows with
  `sentences.translation` untouched.
  → verify: query `translation_remarks` count before/after; diff
  `sentences.translation` hash before/after — unchanged. If Claude's
  limit hits instead, expect the run to EXIT loudly (`[RESET-AT]`,
  Telegram alert, exit code 1), not to skip chunks — re-run after the
  window and note the duplicate-remarks caveat above.

---

## Out of scope (from spec)
No changes to `ai_client_bai.py`, `glossary_builder.py`, `runner.sh`, the
translation path, `--apply` semantics, or the glossary-pair review
pipeline. No new env vars or `.env.example` edits.


---

## Results (2026-10-20)

- Task 3.6 outputs:
  - `timeout 60 uv run pytest -q` → **190 passed in 1.72s** (baseline was 178 passed; +12 new)
  - `pyright src tests` → **0 errors, 0 warnings, 0 informations**
- Task 1.5 dry-run verified: `[model] Using model pool: claude:sonnet` printed,
  no AI call, log dir unchanged (0 files before and after).
- Task 2.1 verified: `just --dry-run review kn claude:sonnet --limit 1` prints
  the exact nohup command; `just --list` shows `review`.
- NOTICED — NOT TOUCHING: verify remarks' `severity` field is not persisted by
  `RemarkWriter` (the `note` column stays empty; severity only feeds the
  printed count). Pre-existing behavior, out of this thread's scope.

- Task 4.0 verified: `data/epitaka_kn_pre_review_20261020.db` exists, opens,
  251,573 sentences; 676 pre-existing remarks.
- Task 4.1 BLOCKED (spec assumption wrong on this machine): local `.env` has
  no `CLAUDE_KEY_1`, so the claude:sonnet pool is empty and the run exits
  loudly before any call ("No claude keys left ... set CLAUDE_KEY_1 in .env"
  → fatal exit, exit code 1 — the specced loud-exit behavior, working as
  designed). The USER must add a non-empty `CLAUDE_KEY_1` line to `.env`
  (any marker value; the Claude path bills the subscription, the key only
  marks the provider as wanted) — the agent never edits `.env`. Then re-run:
  `uv run src/verify_translation.py --lang kn --model claude:sonnet --book Khp --limit 1`
- Translation fingerprint before probe: 251573 rows / 21,553,110 chars.

- Task 2.2 (user follow-up + review round 2, 2026-10-20): added
  `review-kn-claude` / `review-kn-azure` shortcut recipes (full run, no
  limit) — quoted "kn" after the second review caught the bare-word
  variable bug that broke the whole justfile. Fixed: recipes verified via
  `just --dry-run review-kn-azure`.
- Review round 2 fixes (applied): dry-run builds no key pool (works with
  zero keys, per spec); DEFAULT_MODELS pinned against
  book_translator.FALLBACK_MODEL_CHAIN by reading its source text (no
  import); _wait_for_off_peak returns None (return value was meaningless).
  Suite: 191 passed; pyright 0 errors.

- Review round 3 (2026-10-20): severity now SAVED — process_chunk fills the
  remark's `note` with its severity ("wrong"/"critical") before
  RemarkWriter.save, so critical findings are filterable and the module
  header is true (user's choice; supersedes the earlier
  NOTICED-NOT-TOUCHING note). New test: main() with every *_KEY_* env var
  deleted and .env bypassed succeeds on --dry-run (192 passed, pyright 0).
  The review-kn-azure shortcut STAYS: the user asked for it explicitly
  ("review kn with claude, and review kn with azure deepseek ... no limit").

- Review round 4 (claude via herdr, 2026-10-20): no blocker. MEDIUM fixed —
  `just stop` now also pkills "[v]erify_translation.py --lang <lang> " so a
  background review is stoppable (a review's claude -p child is one-shot
  and exits on its own). Dispositions of the LOWs: note-column severity is
  the established convention (glossary pipeline already writes severity
  there; no reader exists) — resolved; in-place remark mutation and the
  book-level skip on a bad remark are pre-existing — NOTICED, not touching;
  review-kn-azure stays (user-requested); the assert-under-`-O` note is
  harmless (only a dry run passes None) — left as is. Also NOTICED while
  fixing: the translator's claude pkill pattern requires "TARGET LANGUAGE:"
  on the command line, but the prompt goes via stdin, so that clause can
  never match — translator-owned, not touched.

- Finalize (2026-10-20): user confirmed the review rounds count as the
  review; evidence recorded in review.md (verdict PASSED). Task 4.1's live
  Claude probe stays open on purpose: blocked on the user adding
  CLAUDE_KEY_1 to the LOCAL .env. Full-corpus reviews are one command
  away: `just review-kn-claude` (after the key) / `just review-kn-azure`
  (ready now), both stoppable with `just stop`.
