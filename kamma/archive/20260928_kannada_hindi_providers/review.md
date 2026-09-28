## Thread
- **ID:** 20260928_kannada_hindi_providers
- **Objective:** Kannada test run (MN10) with a Hindi reference, DeepSeek/OpenRouter providers, uv, no Roman output for Indian languages, and a Pāli + translation text export.

## Files Changed
- `src/book_translator.py` — Hindi reference choice, prompt lines, no-Roman guard, fallback chain, start-up key check
- `src/common/ai_client.py` — provider prefix, provider-aware key rotation, non-Gemini routing, no keys in state files
- `src/common/ai_openai_compat.py` — new: one DeepSeek/OpenRouter `chat()` call
- `src/common/context_builders.py` — Hindi label
- `src/export_text.py` — new: Pāli (target script, ASCII digits) + translation, para by para
- `runner.sh` — uv only; Hindi DB downloaded only for Indian targets; language asked first
- `pyproject.toml`, `uv.lock` — new; `requirements.txt` — deleted
- `README.md`, `.env.example`, `kamma/tech.md` — docs; `tests/` — 6 files, 41 tests

## Findings
| # | Severity | Location | What | Why | Fix |
|---|----------|----------|------|-----|-----|
| 1 | major | `ai_client.py` `_generate_with_retry` | Missing provider key swallowed; run ends "All API keys exhausted" | `runner.sh` sleeps 3 h forever on a typo'd key | Log the reason; start-up check for a pinned model |
| 2 | minor | `ai_client.py` `acquire` | Round-robin index used full-list positions on the provider list | With 2 DeepSeek keys, every Gemini call used GEMINI_KEY_1 | Index within the provider's keys |
| 3 | minor | `ai_client.py` `remove`/`record_result` | Plaintext keys (now paid ones) in world-readable temp state files | Key leak to other local users | Store label + hash only; old files deleted |
| 4 | minor | `runner.sh` | Import check missed aksharamukha; pip path in a uv venv; Hindi DB always downloaded (CodeRabbit) | Broken pip envs; upstream pays for Hindi | uv only (user); Hindi only for Indian targets (user) |
| 5 | minor | `book_translator.py` `NO_ROMAN_LANGS` | 13.6% of existing Hindi rows would fail the rule | Hindi runs retry many lines | Kept by user decision |
| 6 | nit | several | "Gemini key(s)" log text; dead "IS Thai" clause; numeric entities; stale comments/notes; `--no-dev`; 402 untested | Misleading text, gaps | All fixed |
| 7 | nit | user review | Tool-loop guard; `isdigit` crash; Roman example words; source-text test | — | Declined: spec excludes tools; 0 chars can crash (full Unicode scan); 0 Roman in live run; test is the only call-site guard |

## Fixes Applied
- Findings 1–4 and 6 fixed; 5 kept by the user; 7 declined with evidence.
- Also added (user): the run survives no Gemini key and no OpenRouter key.

## Test Evidence
- `uv run pytest` (scope: whole suite, 6 files, 41 tests) → pass
- Revert checks (scope: each new behaviour): Hindi ref 2 fail, provider filter 3, bad-key rule 1, Roman guard 4, review fixes 5 → all fail on revert, pass on restore
- System prompts vs saved originals (scope: vi, th byte-identical; kn, hi, mr change as intended) → pass
- Runner download list (scope: `kn`/`vi`/`hi`) → 1/0/0 Hindi entries
- Live: DeepSeek probe; OpenRouter probe; MN10 `kn` run (scope: all 325 lines) → 325/325 saved, 0 Roman / other-script characters; 1 line dropped and correctly retried
- `export_text.py` on MN10 (scope: 131 paragraphs) → user confirmed the layout
- CodeRabbit (`--agent --uncommitted --include-untracked`, 24 files) → 3 findings, all resolved

## Not Verified
- OpenRouter never did a real translation, only a one-line probe.
- `runner.sh` end to end (only its download list and `bash -n`); the 3 h sleep path.
- Timeout path and real OpenRouter error bodies; `--script` override in the export.
- `glossary_builder.py` / `study_builder.py` beyond how they call the client; Python 3.14 (capped out).
- Kannada translation quality beyond the user's spot check.

## Verdict
PASSED
- Review date: 2026-09-28
- Reviewer: Claude (main session) with an independent subagent, CodeRabbit, and the user's own review
