# Plan: DeepSeek runs wait for off-peak hours

Thread: 20261020_deepseek_off_peak. Read `spec.md` in this folder first: it
holds the verified facts, the decisions and the "done" list behind every step.

## Architecture Decisions
- The wait lives in the translator (`src/book_translator.py`), in
  `_handle_chunk` right before the request (first draft: in the chunk loop;
  moved after review, see Phase 5). Not in `runner.sh`: that would
  need the peak calendar in bash and would cover only runs started through
  the runner. Not in `ai_client`: it has no `--stop-at` and no way to cancel
  a call that is waiting.
- The peak rule stays in one place, `is_peak` in `src/common/costs.py`. The
  new `off_peak_start` is built on it. `is_peak` itself is not changed.
- Gate = `args.model` starts with `deepseek:`. Azure, Gemini, Claude, the
  fallback chain (no `--model`) and `--dry-run` never wait.
- Everything reads the clock as `datetime.fromtimestamp(time.time(),
  timezone.utc)`. `stop_due` already uses `time.time()`, so one fake clock
  drives both in tests. Never `datetime.now()` or local time (spec: the
  server may be in another time zone).
- Deliberately not built: override switch, holiday calendar, new setting,
  `runner.sh` change, gating of other scripts (see spec "not included").
- Tests use no network and no real keys: clear every `*_KEY_*` variable.
  `time.sleep` is faked in tests, so the fake sleep MUST move the fake clock
  on, or the wait loop spins forever. Always run `timeout 60 uv run pytest -q`.

## Phase 1 — The clock rule
- [x] Record the baseline: run the suite before any edit and write the pass
      count here: `Baseline: 139 passed, 1 failed`.
      PRE-EXISTING — NOT CAUSED BY THIS THREAD:
      `tests/test_stats.py::test_weekly_capacity_comes_from_lines_this_week_over_percent_used`
      fails with `Obtained: None`. Its ledger rows are dated 2026-10-03 and
      it reads "the 7 days before now", so since 2026-10-10 the rows are
      outside the window. Run 2026-10-20, keys cleared. Not touched here.
  → verify: `timeout 60 uv run pytest -q` ends with "1 failed, 139 passed"
    and the one failure is the stats test above.
- [x] `kamma/tech.md` (workflow rule: before the code). Add a dated
      2026-10-20 note under "Constraints": a run pinned to a `deepseek:`
      model sleeps through DeepSeek peak hours (01:00-04:00 and 06:00-10:00
      UTC, Mon-Fri; price page read 2026-10-20), UTC only, no override (user
      choice), other providers unaffected. Quote the user: "the server might
      be running on some different time zone, so it needs to be universal".
      Add "waits out peak hours" to the `just run-deepseek` line in "Tools &
      Platforms".
  → verify: `rg -n -i "peak" kamma/tech.md` shows the new lines.
- [x] `src/common/costs.py`: import `timedelta` and add after `is_peak`:
      ```python
      def off_peak_start(t: datetime) -> datetime:
          """First moment at or after t that is off-peak (t in UTC, as is_peak expects)."""
          if not is_peak(t):
              return t
          t = t.replace(minute=0, second=0, microsecond=0)
          while is_peak(t):
              t += timedelta(hours=1)
          return t
      ```
      Add to `tests/test_costs.py` a parametrized test `(input, expected)`,
      all UTC: Mon 2026-09-28 07:00 -> 10:00; 02:30 -> 04:00; 01:00 -> 04:00
      (peak start counts as peak); 06:00 -> 10:00; 04:00, 05:00, 12:00 ->
      unchanged (peak end is exclusive); Fri 2026-10-02 09:59:30 -> 10:00;
      Sat 2026-10-03 07:00 -> unchanged.
  → verify: `timeout 60 uv run pytest -q tests/test_costs.py` passes. Revert
    check: in ONE command, copy `costs.py` to the scratchpad, change the body
    of `off_peak_start` to `return t`, run the test, copy the file back.
    Expect the five peak cases (07:00, 02:30, 01:00, 06:00, 09:59:30) to
    fail; report the real count.
- [x] Phase 1 check.
  → verify: `timeout 60 uv run pytest -q` passes the baseline 139 plus the
    new cases. The only failure is the pre-existing stats test.

## Phase 2 — The wait in the translator
(First draft. Phase 5 changed it: `wait_for_off_peak` now returns a bool and is called
in `_handle_chunk` right before the request, not in the chunk loop. The snippets and
cases below are as first built.)
- [x] `src/book_translator.py`: add `from datetime import datetime,
      timezone` and `import common.costs as costs` (the file's own import
      style; the first draft said `from common import costs`), then add next
      to `stop_due`:
      ```python
      def wait_for_off_peak(args) -> None:
          """DeepSeek charges double at peak: sleep until off-peak, or until --stop-at."""
          if getattr(args, "dry_run", False) or not (getattr(args, "model", None) or "").startswith("deepseek:"):
              return
          now = datetime.fromtimestamp(time.time(), timezone.utc)
          if not costs.is_peak(now):
              return
          print(f"[PEAK] DeepSeek peak hours (01:00-04:00 and 06:00-10:00 UTC, Mon-Fri). "
                f"Waiting until {costs.off_peak_start(now):%Y-%m-%d %H:%M} UTC.")
          while not stop_due(args):
              now = datetime.fromtimestamp(time.time(), timezone.utc)
              if not costs.is_peak(now):
                  return
              # Re-read the clock every slice so the wait follows the wall clock.
              time.sleep(min(300, (costs.off_peak_start(now) - now).total_seconds()))
      ```
      Add `tests/test_off_peak.py` (import style as in `tests/test_stop_at.py`:
      `sys.argv = sys.argv[:1]` before `import book_translator as bt`). A
      fixture holds a fake epoch, and replaces `bt.time.time` (returns it)
      and `bt.time.sleep` (adds the seconds to it). Cases, with
      `types.SimpleNamespace(model=..., dry_run=..., stop_at=...)`:
      1. `deepseek:deepseek-v4-flash` at Mon 2026-09-28 07:00 UTC: the call
         returns with the clock at exactly 10:00 UTC, no single sleep is
         over 300 s, and the output has one `[PEAK]` line naming
         `2026-09-28 10:00 UTC`.
      2. Case 1 again with the machine's zone set to `Pacific/Kiritimati`
         (`monkeypatch.setenv("TZ", ...)` and `time.tzset()`, and `tzset()`
         again when the test ends). Mon 07:00 UTC is Mon 21:00 there.
      3. `stop_at` = 07:10 UTC: returns once the clock is at or past 07:10,
         well before 10:00.
      4. No sleep and no `[PEAK]` line for: `dry_run=True`; `gemini-3.8-flash`;
         `azure:DeepSeek-V4.1-Flash`; `claude:sonnet`; `model=None`; and
         `deepseek:deepseek-v4-flash` at Mon 12:00 UTC.
  → verify: `timeout 60 uv run pytest -q tests/test_off_peak.py` passes.
    Revert check A (ONE command, file backed up in the scratchpad and
    restored in the same command): change the two `timezone.utc` clock reads
    to `datetime.fromtimestamp(time.time())` (local time). Expect case 2 to
    fail and case 1 to pass; report the real result.
- [x] Call it in the chunk loop (the `for c_idx, chunk in enumerate(chunks,
      1):` loop in `process_book`; Phase 3 removed the unused `c_idx`), before
      the existing check:
      ```python
      for chunk in chunks:
          wait_for_off_peak(args)
          if stop_due(args):
              break
      ```
      Add integration tests to `tests/test_off_peak.py`. Copy the book and
      fake-call set-up from `setup` in `tests/test_missing_lines.py` (one
      paragraph, three lines, `ai.call_ai_with_logging` faked, `NoContext`
      stubs), with `args.model` and `args.stop_at` as parameters. The fake
      call records the fake clock. Cases:
      1. `deepseek:` model, clock Mon 07:00 UTC: the first call is at or
         after 10:00 UTC and all three lines are saved.
      2. Same, `stop_at` = 07:10 UTC: no call is made and nothing is saved.
      3. `gemini-3.8-flash`, clock Mon 07:00 UTC: the call is at 07:00.
  → verify: `timeout 60 uv run pytest -q tests/test_off_peak.py` passes.
    Revert check B (ONE command, back up and restore as above): delete the
    `wait_for_off_peak(args)` line from the chunk loop. Expect integration
    cases 1 and 2 to fail and case 3 to pass; report the real count. A
    revert that stops the module importing proves nothing: check the failure
    text names the assertion, not an import error.
- [x] Phase 2 check.
  → verify: `timeout 60 uv run pytest -q` passes (baseline 139 plus all new
    tests); the only failure is the pre-existing stats test. Re-read the
    edited loop region in `process_book` and
    `wait_for_off_peak`: no `datetime.now()` and no local-time call appears.

## Phase 3 — Fix every warning and problem met (added 2026-10-20)
User, 2026-10-20: "Fix all warnings that you come across. Fix all problems.
Don't leave anything for later." This replaces the earlier "noticed, not
touching" notes. Each item: read the exact line, name the mechanism, fix the
cause, never weaken a check.
Method: the Pyright command line from the dpd-db environment
(`/home/bodhirasa/MyFiles/3_Active/dpd-db/.venv/bin/pyright src tests`) reads
this repo's `[tool.pyright]` setting and prints errors. The editor also shows
"not accessed" hints that the command line hides, so those were fixed from
the editor's own list, file by file.
- [x] `tests/test_stats.py::test_weekly_capacity_comes_from_lines_this_week_over_percent_used`:
      its ledger rows were fixed at 2026-10-03 while the code under test
      counts only the 7 days before the reading. The rows are now dated from
      the current time. Every assertion is unchanged.
  → verify: failed on 2026-10-20 before the edit (baseline, `Obtained: None`),
    passes after; the code under test was correct.
- [x] The editor could not see the project's own `.venv`, so it reported
      `google.genai`, `dotenv` and `aksharamukha` as unresolved. Added
      `[tool.pyright]` (`venvPath`, `venv`) to `pyproject.toml`.
  → verify: the Pyright command line resolves all three. The editor still
    lists two of them (`dotenv`, `aksharamukha`) and looks to need a restart
    of its Pyright to read the new setting.
- [x] Test files `test_costs.py`, `test_stats.py`, `test_missing_lines.py`,
      `test_compare_models.py`, `test_off_peak.py`: unused arguments of fake
      functions are now `_` or are used; `None` passed as the key rotator is
      `cast(ai.KeyRotator, None)`; `id_type` and a possibly-`None` result got
      the right type or an `is not None` check; one test now also checks the
      DeepSeek URL it already posted to.
  → verify: the editor lists no warning for these files; the suite passes.
- [x] `src/common/ai_client.py`: `_fatal_all_keys_exhausted` is marked
      `NoReturn` (it ends in `sys.exit`), so the model name is known to be set
      afterwards; `config` and the reply are typed `Any` instead of `object`;
      `timeout` is `float` (the code and a test already pass 0.05); `log` is a
      `Callable`, not the function `callable`; `tool_executor` is typed.
      TWO REAL BUGS found by this and fixed: with no usable models,
      `call_gemini_with_tools` called `log.error` on its own `log` parameter (a
      function), so it raised `AttributeError`; and a reply with no text and no
      tool call hit `getattr(x, None, None)`, which always raises `TypeError`
      (and `[]` or `None` candidates raised `IndexError`/`TypeError`). Both
      now return `None` and log. A tool call with no executor now raises a
      `TypeError` that says why. New `tests/test_gemini_tools.py` (5 cases).
  → verify: revert check, ONE command, the three fixes put back, file
    restored with `cmp`: 5 failed; with the fixes: 5 passed.
- [x] `src/book_translator.py`: stub-module attributes set with `setattr`
      (same effect); `boundaries` typed `list[int]`; a missing para or line id
      in a model reply is skipped before `int()` (same result as the old
      caught `TypeError`); unused counter `c_idx`, unused import
      `GlossaryContext`, and three unused `process_book` arguments
      (`translation_writer`, `glossary_writer`, `remark_writer`) removed with
      the writer objects that only fed them (their constructors only store
      their arguments). NOTE: this changes `process_book`'s signature against
      the upstream code.
  → verify: command-line Pyright 0 errors; suite passes; the two tests that
    called `process_book` were updated; new test for the id guard.
- [x] `src/common/context_builders.py`: module-level `from pathlib import
      Path` (the type notes name it; no run-time effect); `only_langs` is a
      `Collection[str]` (a set was passed); unused `t_niss0` and an unused
      `PRAGMA` read removed; the silent `except Exception as exc` in the
      parallel-translation reader now logs, as its own comment says.
  → verify: command-line Pyright 0 errors; suite passes.
- [x] Files that showed errors only in the whole-project command-line check:
      `cleanup_bleeding.py` (`params` may be a dict), `export_text.py` (a
      `None` from the transliterator now raises a clear `ValueError`; the
      `__doc__` may be `None`; unused loop names), `study_builder.py`
      (`setattr` for stub modules; a dead nested function `_book_name` and
      its cache removed; the no-op logger argument dropped because it equals
      the default).
  → verify: command-line Pyright 0 errors; `python3 -I -m py_compile` on the
    three files; suite passes.
- [x] The one pytest warning (`ast.Str is deprecated`) comes from the pinned
      third-party package `aksharamukha 2.3`. A filter for that exact message
      is in `pyproject.toml`; nothing else is filtered.
  → verify: the suite prints no warning.
- [x] Phase 3 check.
  → verify: `timeout 60 uv run pytest -q`: 168 passed, 0 failed, no warning;
    Pyright command line on `src tests`: 0 errors, 0 warnings.

## Phase 4 — Docs and final checks
- [x] `README.md`: in "DeepSeek and OpenRouter" add a short paragraph: a run
      pinned to a `deepseek:` model sleeps through DeepSeek's peak hours
      (01:00-04:00 and 06:00-10:00 UTC, Mon-Fri) and prints a `[PEAK]` line;
      all in UTC; Chinese public holidays count as peak; the fallback chain,
      Azure and `--dry-run` never wait; there is no override. In "Cost
      ledger", keep the holiday sentence true: say the wait also treats them
      as peak. `justfile`: append "Waits out DeepSeek's peak hours." to the
      one-line descriptions of `run-deepseek`, `next` and `next-deepseek-kn`.
  → verify: `rg -n -i "peak" README.md justfile` shows the new lines in all
    four places; `just --list` shows the three recipes with the new text.
- [x] Run every checker the repo declares.
  → verify: `pyproject.toml` declares only `pytest` as a dev tool and the
    repo has no pre-commit config, so `timeout 60 uv run pytest -q` is the
    full set: 168 passed, no failure, no warning. Pyright (not declared, but
    run from the dpd-db environment) reports 0 errors.

## Phase 5 — Review fixes and the model name (added 2026-10-20)
Reviews: Sonnet subagent, CodeRabbit (`--uncommitted --include-untracked
--fresh`, free allowance, permission from the user's review command), and a
second agent's report pasted by the user. No blocking or major finding. Every
finding was checked against the code before it was applied.
- [x] Gate moved from the chunk loop to just before the request in
      `_handle_chunk`, and `wait_for_off_peak` returns a bool (CodeRabbit 2:
      the clock was read before the prompt was built; reviewer 3: retries
      bypassed the gate). A split and a missing-lines retry now wait too. The
      Sonnet reviewer's opposite view (retries should not wait) was weighed:
      the user wants DeepSeek only off-peak, and each reply is saved before the
      next request, so a wait loses nothing.
  → verify: tests for a prompt built across 06:00 and a retry after peak
    starts; revert check M1 (gate removed): 4 failed, 20 passed.
- [x] Sleep slice cut at `--stop-at` (CodeRabbit 1, reviewer 3.1, Sonnet 1);
      no `[PEAK]` line when the stop time is already past (Sonnet 4, reviewer
      3.2); the line is flushed (Sonnet residual risk).
  → verify: revert checks M2 (clamp removed): 1 failed; M3 (early return
    removed): 1 failed; M4 (local-time clock reads): 10 failed.
- [x] Tests: `tests/test_off_peak.py` rewritten (23 cases, clears the key
      variables itself, a start off the 5-minute mark, stop times inside a
      slice, a stop time already past); `tests/test_missing_lines.py` clears
      the key variables too (AGENTS.md rule, Sonnet 3). Two new guard tests:
      the parallel-translation reader logs a failure; a transliterator that
      returns nothing raises.
  → verify: revert checks, files restored with `cmp`: reader warning removed:
    1 failed; export guard removed: 1 failed.
- [x] Orphans left by this thread removed (Sonnet 5): the unused
      `GlossaryWriter` class and the import only it used, seven redundant local
      `Path` imports, a commented-out debug line that named the removed timer.
      `TranslationWriter` and `RemarkWriter` stay (`verify_translation.py`
      uses them). `GlossaryContext` was unused before this thread and is left.
  → verify: `rg` finds no leftover; Pyright 0 errors.
- [x] Docs (Sonnet 6): README and tech notes say what the code does (calls
      "almost all" at half price; the relay case; the new settings; how to run
      Pyright); one wrong README line about `just run` fixed (it is the
      Claude-then-Azure relay), and the same wrong text in the tech notes.
  → verify: read back.
- [x] Model name (user request): `deepseek:deepseek-v4-flash` ->
      `deepseek:deepseek-flash` in the three `justfile` recipes, the fallback
      chain and its help text, README, `.env.example`, a `runner.sh` comment
      and a docstring. NOT changed: every Azure name; `ai_client_bai.py` (a
      different provider); `costs.PRICES` (keeps the old key). Two existing
      tests that pinned the chain's old name now expect the new one. New
      `tests/test_deepseek_model_name.py` (3 cases; one pins the Azure name).
  → verify: putting the old name back in the `justfile` and the chain fails 4
    tests; restored with `cmp`.
- [x] Phase 5 check.
  → verify: `timeout 60 uv run pytest -q`: see Results; Pyright: 0 errors.

## Phase 6 — Your checks (you run them; I do not)
OPEN AT FINALIZE (2026-10-20): neither check below has been run. The code and
its tests are done and reviewed; these two checks need a real peak hour and a
working DeepSeek key. Run them later and note the result in `kamma/tech.md`.
- [ ] Peak check, at the next real peak. Wednesday 2026-10-21 has peak at
      01:00-04:00 and 06:00-10:00 UTC (06:30-09:30 and 11:30-15:30 in Sri
      Lanka). Run `cd /home/bodhirasa/MyFiles/3_Active/epitaka-translator &&
      just next-deepseek-kn`, wait for the first output, then press Ctrl+C.
  → verify: the output has a `[PEAK] ... Waiting until ... UTC.` line and no
    `[cost]` line. If the run ends with the "natural pause" or "Nothing to
    do" message, no chunk was pending: tell me, and we pick a book that is.
- [ ] Off-peak billing check, in any off-peak hour. User, 2026-10-20: the
      DeepSeek key is hitting its limit, so no real call can be made now;
      this check waits until the key works again. No code task depends on it.
      Nothing else may use the
      DeepSeek key meanwhile (the dpd-db project uses the same key; checked
      2026-10-20, no value printed). Type `/deepseek-balance` and note the
      balance. Run `cd /home/bodhirasa/MyFiles/3_Active/epitaka-translator &&
      just next-deepseek-kn` until `just stats day kn` shows at least $0.20
      for DeepSeek (about 20 calls: the old ledger averages $0.0149 a call,
      n = 257, about 35 s a call). Press Ctrl+C, then type `/deepseek-balance`
      again. The run writes to the local copy of the data, which the next
      `just pull` overwrites.
  → verify: the balance drop is within about $0.02 of the ledger's DeepSeek
    total. A drop near double the ledger total means off-peak is not billed
    at half: tell me, because the premise of this thread then needs another
    look. Write both numbers in the Results section below.

## Results
(filled in during `/kamma:2-do`, 2026-10-20)
- Baseline: 139 passed, 1 failed (the stats date test, fixed in Phase 3).
- Phase 1: `off_peak_start` with 9 cases. Revert check (body replaced by
  `return t`, restored with `cmp`): 5 failed, 4 passed, the five being the
  peak cases 07:00, 02:30, 01:00, 06:00 and 09:59:30.
- Phase 2: 10 unit cases and 3 chunk-loop cases in `tests/test_off_peak.py`.
  Revert check A (clock read as local time): 3 failed, 7 passed. The failures
  are the Kiritimati case, the Los Angeles case, and the stop-time case (this
  machine is UTC+5:30, so it is not UTC either); the UTC case passes. Revert
  check B (the call removed from the chunk loop): 2 failed (the deepseek wait
  case and the stop-time case), 11 passed. Both files were restored with
  `cmp`.
- Phase 3: see the list above. Final: 168 passed, 0 failed, no warning;
  Pyright command line on `src tests`: 0 errors.
- MISTAKE, mine: one test command contained a stray empty `export`, which
  printed this shell's whole environment into the session output, including a
  GitHub token, a Context7 key and a Claude Code session token. Nothing was
  sent anywhere on purpose. The user was told to rotate the GitHub token and
  the Context7 key if the transcript is stored or shared.
- Not run: the two live checks in Phase 6. The DeepSeek key is at its limit.
- Review, 2026-10-20 (Sonnet subagent, CodeRabbit, the user's second agent):
  no blocking or major finding; minor findings fixed in Phase 5. Two claims in
  the pasted review were wrong and were not applied: `is_peak` reports a
  Chinese holiday as peak (checked), and the client has no sleep longer than
  20 s (checked; the 3 h sleep is `runner.sh`, a new process that checks again).
- Phase 5 revert checks (files restored with `cmp`): dispatch gate removed: 4
  failed, 20 passed; stop-time clamp removed: 1 failed; early stop return
  removed: 1 failed; clock read as local time: 10 failed (this machine is
  UTC+5:30); reader warning removed: 1 failed; export guard removed: 1 failed;
  old DeepSeek name back in the `justfile` and chain: 4 failed.
- Final: `timeout 60 uv run pytest -q`: 178 passed, 0 failed, no warning
  (keys cleared). Pyright command line on `src tests`: 0 errors, 0 warnings.
  `python3 -I -m py_compile` on every source file: ok. `just --list` shows the
  three DeepSeek recipes with the new text. Azure names unchanged.
- CORRECTION to my own earlier statement: I said the verification script's
  default model would move to `deepseek-flash`. That script uses the B.AI
  gateway, a different provider with its own model names, so it was left alone.
- Not verified: the two live checks (Phase 6; the DeepSeek key is at its
  limit); which DeepSeek version answers a call; whether DeepSeek bills a
  request by its start or end time (a request started just before 10:00:00
  UTC, or a server clock ahead of DeepSeek's, may be billed at peak: the
  billing check will show it, and no safety margin was added); Python 3.10 and
  3.11 (the venv is 3.13); the editor's own warnings (its Pyright needs a
  restart to read the new setting; the command line reports 0).
