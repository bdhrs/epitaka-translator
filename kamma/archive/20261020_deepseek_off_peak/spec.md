# Spec: DeepSeek runs wait for off-peak hours

Thread: 20261020_deepseek_off_peak
Request (user, 2026-10-20): "i want to use the deepseek api. but only when it
is offpeak. can you set that up"

## Overview
DeepSeek's own API costs half price off-peak and full price at peak. Make a
translator run that is pinned to a `deepseek:` model sleep through peak hours
and carry on when off-peak starts. The rule uses UTC only, so it behaves the
same on any machine, whatever its time zone (user, 2026-10-20: "the server
might be running on some different time zone, so it needs to be universal").

## Decisions (question round, 2026-10-20)
- Scope: only runs pinned to a `deepseek:` model. The main background run
  (`just run`, Claude then `azure:DeepSeek-V4.1-Flash`) stays as it is.
- No override. DeepSeek always waits for off-peak. This removes today's
  ability to run DeepSeek at any hour; the user accepted that.
- Added mid-thread, 2026-10-20 (user): "Fix all warnings that you come
  across. Fix all problems. Don't leave anything for later." Every editor
  warning and test failure met in this thread is fixed in the thread, even
  when it was there before. Plan Phase 3 lists them.
- Added after review, 2026-10-20 (user): "Please make sure that azure does
  not get changed. I don't think it has that latest model". Every Azure name
  stays as it is, in the code, the tests and the docs.
- Added after review, 2026-10-20 (user): "I don't want to have to keep
  updating the name ... it always just points to the correct model." The
  direct DeepSeek API is called as `deepseek:deepseek-flash`, DeepSeek's
  version-free name for its newest Flash model (change log 2026-10-17; the
  old `deepseek-v4-flash` is only routed "temporarily", change log
  2026-09-10). Changed in the three DeepSeek recipes of `justfile` and in the
  fallback chain. `src/common/ai_client_bai.py` talks to a different provider
  (B.AI) with its own model names and is not changed. `costs.PRICES` keeps
  the old name so a hand-typed old name is still priced.

## Current behaviour (read from code, commit 2e8d45a)
- `justfile`: `run-deepseek`, `next` and `next-deepseek-kn` call
  `./runner.sh <lang> deepseek:deepseek-v4-flash [next]`. `runner.sh` passes
  the model on as `--model` to `src/book_translator.py`. `relay`/`run` use
  `claude:sonnet+azure:DeepSeek-V4.1-Flash`.
- DeepSeek is called at any hour.
- `is_peak(t)` in `src/common/costs.py` already holds the peak rule and the
  ledger prices off-peak at half. Nothing else in the repo knows the rule.
- `process_book` in `src/book_translator.py` loops over chunks and calls
  `stop_due(args)` before each one. The only API call of a translator run is
  `ai.call_ai_with_logging` inside `_handle_chunk`. A `--dry-run` returns
  from `_handle_chunk` before that call.
- `--stop-at <unix time>` ends the run after the current chunk with a
  `[STOP-AT]` line and exit 0. `runner.sh` reads that line.

## What it should do
1. Add `off_peak_start(t)` to `src/common/costs.py`, next to `is_peak`: the
   first moment at or after `t` that is off-peak. Built on `is_peak`, so the
   rule stays in one place.
2. Add `wait_for_off_peak(args)` to `src/book_translator.py`. It returns True
   at once when `args.dry_run` is set, when `args.model` does not start with
   `deepseek:`, or when it is off-peak. In peak it returns False at once if
   `stop_due(args)` already holds. Otherwise it prints one `[PEAK]` line (the
   rule and the UTC time the wait ends, flushed) and sleeps in slices of at
   most 300 s, cut short at `--stop-at`, until off-peak (True) or until the
   stop time (False).
3. Call it in `_handle_chunk`, right after the dry-run return and right
   before `ai.call_ai_with_logging`. If it returns False, `_handle_chunk`
   returns `(0, 0, 0)` and sends nothing; the chunk loop's own `stop_due`
   check then ends the run through the existing `[STOP-AT]` path. (Changed
   after review, 2026-10-20: the first draft called it in the chunk loop,
   which left the prompt-building time, and any split or retry, outside the
   check. The user's goal is DeepSeek only when off-peak.)
4. Every request re-checks, so a split or a retry for missing lines waits
   too. This loses no work: each reply is saved before the next request is
   made. A request already on its way finishes, even if peak starts while it
   runs. What is left: that request itself (median 35 s between calls, 256
   gaps in the old DeepSeek ledger, 90th percentile 50 s), the short wait for
   a free key inside the client, and its 20 s back-off after an error.
5. Time zone rule: every check uses UTC (`datetime.fromtimestamp(time.time(),
   timezone.utc)`), never `datetime.now()` or the local time. The sleep slice
   re-reads the clock, so a suspended machine or a clock change cannot
   oversleep. `is_peak` itself is not changed.
6. Docs: `kamma/tech.md` (before the code), the README DeepSeek section, and
   the one-line descriptions of the three DeepSeek recipes in `justfile`.

## Assumptions & uncertainties
Verified this session:
- DeepSeek pricing page (api-docs.deepseek.com/quick_start/pricing), fetched
  2026-10-20: off-peak is half of peak; peak is 01:00-04:00 and 06:00-10:00
  UTC, Monday-Friday, "excluding Chinese public holidays. All other hours are
  off-peak, including weekends and Chinese public holidays in full".
  `is_peak` matches this.
- The only API call site in the translator is the one named above (grep of
  `src/book_translator.py`, `context_builders.py`, `common_utils.py`).
- Azure has no off-peak price (README, `costs.py`), so it is out of scope.
- `.env` here holds a `DEEPSEEK_KEY_1` (name checked, value not read).
Not verified:
- Billing may not match the page. `kamma/lessons.md`, 2026-09-29: the ledger
  said an off-peak run cost half, but the DeepSeek balance fell by the full
  peak price; the cause was never found. The plan ends with a balance check.
- The server's DeepSeek key: the notes say it had none on 2026-10-09.
- A running process keeps its old code. Restart a run to get the wait.
Chosen, not asked:
- Chinese public holidays count as peak (same gap as the ledger). The run
  waits longer than needed on those days. It never pays the peak price by
  mistake.
- The fallback chain (no `--model`) is not gated. No recipe uses it, and it
  reaches DeepSeek only after six Gemini models run out.

## Constraints
- Never edit `.env`. Tests clear every `*_KEY_*` variable and make no network
  call.
- Tests stub `time.sleep`, so the fake sleep must move the fake clock on.
  Run the suite as `timeout 60 uv run pytest -q`.
- No timer, service, cron job, `runner.sh` change or new setting.

## How we'll know it's done
- `off_peak_start` gives: Mon 07:00 -> Mon 10:00; Mon 02:30 -> Mon 04:00;
  Mon 05:00, Mon 12:00 and Sat 07:00 -> unchanged; Fri 09:59 -> Fri 10:00.
- With a fake clock at Mon 07:00 UTC and a pinned `deepseek:` model, no chunk
  is translated until the fake clock reaches 10:00 UTC.
- The same test passes with the machine's time zone set to `Pacific/Kiritimati`
  (UTC+14), where Mon 07:00 UTC is Mon 21:00 local.
- A `--stop-at` inside the peak window ends the wait and the run prints
  `[STOP-AT]`.
- No wait for: `--dry-run`, a Gemini, Claude or Azure model, or no `--model`.
- Reverting the `wait_for_off_peak` call makes the new tests fail (count
  reported). The full suite passes.
- User check at the next real peak (a weekday 01:00-04:00 or 06:00-10:00 UTC):
  start `just next-deepseek-kn`; it prints `[PEAK]` and writes no `[cost]` line.
- User check at off-peak: one short real DeepSeek run, and the balance drop
  matches the ledger's half price (`/deepseek-balance` before and after).

## What's not included
- Gating the fallback chain, `compare_models.py`, or `verify_translation.py`
  (the last one uses the B.AI client, not DeepSeek's own API).
- Changing the relay or the Azure backup.
- A Chinese holiday calendar.
- An override switch.
- Renaming `deepseek-v4-flash` to `deepseek-flash` (the page says the old
  name is still accepted and billed at the Flash price).

## Review outcome (2026-10-20)
Three independent reviews (Sonnet subagent, CodeRabbit, a second agent chosen
by the user) found no blocking or major problem. The minor findings changed
the design in one place (item 3 above) and added tests; the plan's Phase 5
lists each one.
