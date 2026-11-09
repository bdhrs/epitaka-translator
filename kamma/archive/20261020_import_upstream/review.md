# Review: import upstream 5d463fb

**Verdict: PASSED** (2026-11-09)

## Files Changed

- `.agents/skills/import-upstream/SKILL.md`, `.agents/skills/import-upstream/UPSTREAM_LOG.md`, `.claude/skills/import-upstream` (new)
- `.env.example`, `README.md`, `kamma/tech.md`
- `src/book_translator.py`, `src/common/ai_client.py`, `src/common/common_utils.py`, `src/export_text.py`
- `tests/test_export_text.py`, `tests/test_pali_script.py` (new), `tests/test_quota_guards.py` (new), `tests/test_verify_model_choice.py`

## Findings

- CodeRabbit (`--committed --base-commit b305270 --fresh`, 14 files): 1 minor finding. The skill's log step ran only after a port landed, so a study with only skips left the checkpoint in place.
- Own check: a test that proved little (a run ending never trips the stop) was removed. It passed with or without the stop code.
- Privacy scan found a server address in `kamma/tech.md` and a home-folder path in `kamma/tech.md`, `spec.md` and `plan.md`. All were replaced with placeholders.

## Fixes Applied

- The skill's log step now records skip-only studies and keeps the checkpoint before any pending port.
- The weak test was dropped. A type error in `tests/test_verify_model_choice.py` was fixed.

## Test Evidence

- `timeout 60 uv run pytest -q`: 215 passed (206 after the weak test was dropped, then 9 added in Phase 2).
- Pyright: 0 errors, 0 warnings.
- Revert check for Phase 1: with the whitespace guard and the stop rule removed, 2 of the 3 new tests failed. The third was the weak test, now dropped.
- Not done: the Phase 2 tests were not reverted to confirm they fail.
