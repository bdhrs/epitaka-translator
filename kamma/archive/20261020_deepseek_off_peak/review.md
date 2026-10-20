## Thread
- **ID:** 20261020_deepseek_off_peak
- **Objective:** A run pinned to a `deepseek:` model sleeps through DeepSeek's peak hours (UTC only) and carries on at off-peak; plus every warning and problem met in the thread fixed, and the direct DeepSeek API called by its version-free name.

## Files Changed
- `src/common/costs.py` — `off_peak_start`, built on `is_peak`.
- `src/book_translator.py` — `wait_for_off_peak` (bool), called in `_handle_chunk` right before the request; stub-module `setattr`; typing; id guard in `_unanswered`; three unused `process_book` arguments removed; fallback chain uses `deepseek:deepseek-flash`.
- `src/common/ai_client.py` — `NoReturn`/`Any`/`Callable`/`float` typing; fixes for two real bugs in `call_gemini_with_tools`.
- `src/common/context_builders.py` — `Collection` type, module-level `Path`, dead code removed (`GlossaryWriter`, a timer, a PRAGMA read, redundant imports), the reader now logs a failure.
- `src/cleanup_bleeding.py`, `src/export_text.py`, `src/study_builder.py` — type fixes; a dead helper removed; clear error when the transliterator returns nothing.
- `pyproject.toml` — `[tool.pyright]`, one `filterwarnings` entry. `justfile`, `runner.sh` (comment), `.env.example`, `README.md`, `kamma/tech.md` — name, behaviour and settings documented.
- Tests: new `test_off_peak.py`, `test_gemini_tools.py`, `test_parallel_reader.py`, `test_deepseek_model_name.py`; edited `test_costs.py`, `test_stats.py`, `test_missing_lines.py`, `test_compare_models.py`, `test_retry_routing.py`, `test_export_text.py`.

## Findings
Three reviewers: Sonnet subagent, CodeRabbit (fresh, uncommitted + untracked), a second agent (pasted by the user). No blocking, no major.
| # | Severity | Location | What | Why | Fix |
|---|----------|----------|------|-----|-----|
| 1 | minor | `book_translator.py` wait loop | Sleep slice ignored `--stop-at` | Hand-back up to 5 min late | Slice cut at the stop time. Fixed |
| 2 | minor | chunk loop call site | Clock read before the prompt was built; split/retry unchecked | A request could go out at peak price | Gate moved to just before the request. Fixed |
| 3 | minor | `tests/test_off_peak.py`, `test_missing_lines.py` | Did not clear `*_KEY_*` | AGENTS.md rule; real keys loaded by `.env` | Autouse fixture in both. Fixed |
| 4 | minor | wait function | `[PEAK]` printed when stop already due | Misleading log | Early return; line flushed. Fixed |
| 5 | minor | `context_builders.py` | Orphans of this thread | Dead code | `GlossaryWriter` etc. removed. Fixed |
| 6 | minor | README, tech.md | Overstated or stale text | Wrong docs | Rewritten. Fixed |
| 7 | nit | two guards | Untested | Could regress unseen | Tests added; each fails on revert. Fixed |
Not applied (checked, wrong): "`is_peak` says off-peak on Chinese holidays" (it says peak); "client loops can sleep hours" (longest is 20 s). Not applied (judgment): `log(...)` instead of the module logger, because that callback defaults to a no-op and would lose the error.

## Fixes Applied
- All of the above, plus the user's mid-review requests: Azure untouched; direct DeepSeek name changed to `deepseek-flash` (DeepSeek's change log, 2026-10-17) with a guard test; the B.AI client left alone.

## Test Evidence
- `timeout 60 uv run pytest -q` (scope: whole suite, 178 tests, `*_KEY_*` variables cleared, calls faked) → 178 passed, 0 failed, no warning
- `pyright src tests` from the dpd-db environment (scope: 33 project files, reads this repo's pyproject) → 0 errors, 0 warnings
- Revert checks, files restored with `cmp`: gate removed 4 failed; stop clamp 1; early return 1; local-time clock 10; reader log 1; export guard 1; old name back 4
- Sonnet probes: `off_peak_start` vs minute scan, 138,240 instants, 0 mismatches; wait loop, two weeks of starts, 0 bad

## Not Verified
- The two live checks (peak check; off-peak billing check): the DeepSeek key is at its limit.
- Which DeepSeek version answers a call, and whether billing uses a request's start or end time (clock skew or a request near 10:00:00 UTC could cost the peak price). No safety margin added.
- Azure's deployment version (the owner's).
- Python 3.10/3.11; the editor's own warnings (its Pyright needs a restart; the command line reports none).
- Process note: one of my commands printed the shell environment, including three tokens, into the session. The user was told to rotate the GitHub and Context7 keys.

## Verdict
PASSED
- Review date: 2026-10-20
- Reviewer: Sonnet subagent, CodeRabbit CLI, the user's second agent; fixes and verification by Claude (Sonnet 5.5)
