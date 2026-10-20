# Review — 20261020_verify-model-choice

Verdict: **PASSED**

Reviews were run across four rounds (2026-10-20): three relayed through the
user from an independent reviewing agent, and round 4 conducted directly by
the Claude pane (w18:pS) via `herdr agent prompt`. This file records that
evidence; no separate /kamma:3-review session was run, per the user
("you have done the review already").

## Files changed
- `src/verify_translation.py` — rewired from ai_client_bai to the ai_client
  provider stack
- `justfile` — `review` + `review-kn-claude`/`review-kn-azure` recipes;
  `stop` extended to stop review runs
- `tests/test_verify_model_choice.py` — new (13 tests)
- `kamma/tech.md` — dated note on the verifier's provider stack
- `kamma/threads/20261020_verify-model-choice/{spec,plan}.md`

## Findings and fixes
- R1: tests would inherit real .env keys → `load_dotenv()` moved inside
  `main()`; broken justfile dry-run check → variadic `*flags`; foreground
  recipe → background relay; off-peak gate first-model-only limitation and
  Claude-limit loud-exit documented; no remark dedupe → DB snapshot rule;
  `--api-keys` cut. All applied.
- R2: bare `kn` in the two shortcut recipes broke the whole justfile →
  quoted; dry-run needed keys → pool skipped on dry-run; DEFAULT_MODELS
  drift → source-text comparison test; gate return value unused → returns
  None; severity lost in DB → user chose "save severity into note".
- R3: no-keys dry-run test missing → real-`main()` test added; Azure
  shortcut questioned → kept (user-requested); severity → applied.
- R4 (Claude via herdr): "No blocking bug found." MEDIUM: `just stop`
  didn't stop review runs → pkill line added. LOWs: note-column severity
  matches the glossary pipeline convention (no reader exists) — resolved;
  in-place remark mutation and book-level skip — pre-existing, not
  touching; Azure shortcut — stays; assert under `python -O` — harmless.

## Test evidence
- `timeout 60 uv run pytest -q` → 192 passed in 1.73s (baseline 178)
- pyright `src tests` → 0 errors, 0 warnings
- `just --list` parses; `just --dry-run review-kn-azure`, `stop kn` print
  the exact commands
- Live dry-run verified (no AI call, no log files); live Claude probe NOT
  run locally — local `.env` lacks `CLAUDE_KEY_1` (user's to add); the
  DB snapshot `data/epitaka_kn_pre_review_20261020.db` was taken first

## Final verdict
PASSED — all findings fixed or explicitly dispositioned; known limitations
written down in spec.md items 5, 8, 9, 11, 12.
