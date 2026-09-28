# Plan: Kannada test run with a Hindi reference and DeepSeek/OpenRouter providers

Spec: `kamma/threads/20260928_kannada_hindi_providers/spec.md`

Tasks marked **(user runs)** need the translator or a live API call. The agent
writes the exact command; the user runs it and pastes the output; the agent
reads the output against the verify line.

## Phase 1 — uv and test setup

- [x] 1.1 Add `pyproject.toml` with the pinned deps from `requirements.txt`
      and a `dev` group with `pytest`. Run `uv lock`.
      → verify: `uv sync` succeeds; `uv run python -c "import google.genai, dotenv, requests"` exits 0; the dep pins in both files match.
- [x] 1.2 Put `src/` on the test import path (the scripts import
      `common.ai_client` with `src/` as the script dir) via pytest's
      `pythonpath` setting in `pyproject.toml` — no `conftest.py` needed — and
      add one smoke test that imports `ai_client`, `common_utils` and
      `context_builders`.
      → verify: `uv run pytest` passes with 1 test.
- [x] 1.3 `runner.sh`: use `uv sync` / `uv run` when `uv` is on PATH; keep the
      venv + pip branch otherwise.
      → verify: read both branches; `bash -n runner.sh` exits 0; the pip branch cannot run against a uv-made `.venv`.
- [x] 1.4 Phase check.
      → verify: `uv run pytest` green; `git diff --stat` shows only the files above.

## Phase 2 — Hindi reference

- [x] 2.1 Add `epitaka_hi.db|epitaka_hi.zip` to `REQUIRED_FILES` in
      `runner.sh`, and `"epitaka_hi.db": "Hindi translation"` to
      `_EPITAKA_LABELS`.
      → verify: `rg -n epitaka_hi runner.sh src` shows both lines.
- [x] 2.2 Add one function in `book_translator.py` that returns the parallel
      reference DB set for a target language (Indian except Hindi → en/hi/si;
      else en/th/si), and use it for `only_langs`.
      → verify: tests for `kn`, `mr`, `hi`, `vi`, `th` assert the exact set; revert the call site to the literal and the `kn` test fails.
- [x] 2.3 Build the reference-language names in `_build_system_prompt` from
      the same function: the block 6 line and the "Devanagari does not
      appear" sentence.
      → verify: tests assert the `kn` prompt names Hindi, not Thai, and lacks "Devanagari does not appear"; the `vi` prompt is byte-identical to before the change.
- [x] 2.4 Phase check.
      → verify: `uv run pytest` green; `rg -n "English/Thai/Sinhala" src/book_translator.py` shows no prompt-text hit left for Indian targets.
      Result: 9 passed; revert of 2.2/2.3 fails 2 tests; vi/hi/th system prompts byte-identical to before; no hits for the literal.

## Phase 3 — DeepSeek and OpenRouter providers

- [x] 3.1 Add `src/common/ai_openai_compat.py` with one `chat()` function
      for DeepSeek and OpenRouter returning `(text, status, error)`.
      → verify: tests with a faked `requests.post`: success, HTTP 429, HTTP 200 with no text.
- [x] 3.2 `make_rotator` loads `DEEPSEEK_KEY_<N>` / `OPENROUTER_KEY_<N>`;
      `KeyRotator` knows each key's provider and `acquire` filters by the
      model's provider prefix, raising at once when there are none.
      → verify: tests: a DeepSeek model never gets a Gemini key; no DeepSeek key raises at once naming `DEEPSEEK_KEY_1`; a DeepSeek-only env builds a rotator. Revert the filter and a test fails.
- [x] 3.3 `_generate_with_retry` routes prefixed models to `chat()` (429 →
      strike, 401/402/403 → remove key); append the two models to
      `FALLBACK_MODEL_CHAIN`.
      → verify: tests with a faked `chat()`: 3× 429 moves the pool on; 401 removes that key only. `rg -n "All API keys exhausted" src/common/ai_client.py` still hits.
- [x] 3.4 **(agent ran, at user request)** Probe: one small call to each new model with a
      large `max_tokens`, to learn DeepSeek's output cap and confirm
      `stealth/space-bunny-alpha` exists.
      → verify: both calls return text; set the DeepSeek `max_tokens` from the result and record the limits in the spec's uncertainties.
      Result 2026-09-28: deepseek `('Hi!', 200, '')`, openrouter `('Hi! 👋', 200, '')`, both with max_tokens=65536. DeepSeek accepted 65536, so the 8192 cap was removed.
- [x] 3.5 Update `.env.example` with the new key variables.
      → verify: every env var the new code reads (`rg -n "environ" src/common`) appears in `.env.example`.
- [x] 3.6 Phase check.
      → verify: `uv run pytest` green; a bare-name Gemini run path is unchanged (existing tests plus reading the diff of `_generate_with_retry`).
      Result: 22 passed. A bare name gives `split_model -> ("gemini", model)`, so the Gemini call gets the same model string as before; the only other Gemini-path change is the `or (provider != "gemini" ...)` clause, which is false for Gemini. (3.4, the probe, was run later the same day.)

## Phase 4 — Kannada script: no Roman output, Pāli + translation text file

- [x] 4.1 Add `aksharamukha` to `pyproject.toml` and `requirements.txt`; `uv lock`; `uv sync`.
      → verify: `uv run python -c "from aksharamukha import transliterate as t; print(t.process('IASTPali','Kannada','Evaṃ me sutaṃ'))"` prints `ಏವಂ ಮೇ ಸುತಂ`; the pins match in both files.
- [x] 4.2 Prompt line for Indian targets: no Roman letters; kept Pāli terms, including the `(<i>pali term</i>)` quote, in the target script.
      → verify: tests: the `kn` prompt has the line; the `vi` system prompt is still byte-identical to the saved one.
- [x] 4.3 Roman-letter guard in both script-bleed checks for the Indian targets, ignoring HTML tags.
      → verify: tests flag `nibbāna` and `Buddha` in `kn`, pass Kannada with `<b>`/`<i>` and digits, leave `vi` alone. Revert the guard and the `kn` tests fail.
- [x] 4.4 Add `src/export_text.py` (plain text, para by para: Pāli in the target script, then the translation, then a blank line).
      → verify: a test with a tiny pair of fixture DBs finds `ಏವಂ ಮೇ ಸುತಂ` followed on the next line by the translation; `uv run src/export_text.py --help` works.
- [x] 4.5 README: the no-Roman rule, the export command, the Aksharamukha dependency and the gloss-romanising repair.
      → verify: the README command matches the export script's `--help`.
- [x] 4.6 Phase check.
      → verify: `uv run pytest` green.
      Result: 30 passed; revert of the guard fails 4 tests; vi/th prompts byte-identical, hi gains the no-Roman line on purpose. Found: aksharamukha 2.3 imports `ast.Str` (removed in Python 3.14), so `requires-python` is capped `<3.14`. Gloss romanising now works (`သေယျထာပိ` → `seyyathāpi`).

## Phase 5 — Docs and the Kannada run

- [x] 5.1 README: uv setup and commands, Hindi reference rule, providers and
      key names, the Devanagari gap for Marathi/Nepali. Update `kamma/tech.md`
      if anything differs from it.
      → verify: every command in the README's changed sections matches a real flag in `--help`.
- [x] 5.2 **(agent runs, at user request)** Download data (done by hand, 2026-09-28). MN10 is
      `M-i` paras 280–410 (user request 2026-09-28: test on a prose sutta, MN10,
      instead of `Dhp`). Dry run:
      `uv run src/book_translator.py --lang kn --books M-i --start 280 --end 410 --max-parts 1 --dry-run --log-dir <dir>`.
      → verify: the logged prompt has a Hindi reference block, no Thai block, and no "Devanagari does not appear" line.
      Result: exit 0, one section of 52 sentences. User prompt has [English translation], [Hindi translation], [Sinhala translation], zero Thai characters. The system prompt is not printed in a dry run; its no-Roman line and script note are covered by tests. Gloss now romanised (`ekaṃ: သော။ | samayaṃ: ၌။ ...`); the para-280 heading entry is plain text and stays Myanmar, as before.
- [x] 5.3 **(agent runs)** One live section: the same command without
      `--dry-run`, plus `--model deepseek:deepseek-v4-flash`.
      → verify: the response parses; translations are saved to `epitaka_kn.db`; count the wrong-script drops in the output and read two saved rows for Kannada script.
      Result: exit 0; paras 280–300, 52 translations parsed and saved, 0 script-bleed dropped, 30 glossary terms, 0 remarks; prompt 168 KB, response 38 KB (not truncated). All 52 rows Kannada script, 0 with Roman outside tags.
- [x] 5.4 **(agent runs)** Whole sutta: the same command without `--max-parts`.
      → verify: the run ends without a crash; a query on `epitaka_kn.db` shows every MN10 line in `<a>..<b>` translated; no saved row contains Devanagari, Thai, Sinhala or Myanmar script, or a Roman letter outside HTML tags.
      Result: first pass saved 272 more lines; 1 dropped (p374 L1: the English word "born" inside Kannada — the Roman guard working). Warning text updated to mention Roman letters. A resume run filled it. Final: 325/325 rows, 0 empty, 0 Roman / Devanagari / Thai / Sinhala / Myanmar outside tags.
- [x] 5.5 Text file for MN10: `uv run src/export_text.py --lang kn --book M-i --start 280 --end 410 --out <file.txt>`.
      → verify: one block per paragraph 280–410; each block's Pāli is in Kannada script with no Roman letters and is followed by a Kannada translation; the user opens it and confirms.
      Result: `artifacts/mn10_kn.txt`, 131 paragraph blocks, every block has a translation, 0 Roman letters, digits ASCII (user asked 2026-09-28). User confirmed the layout 2026-09-28.
- [x] 5.6 Phase check.
      → verify: `uv run pytest` green; spec's "How we'll know it's done" items each ticked with the output that proves them.
      Result: 30 passed. Done-criteria: tests + revert checks (2.x, 3.x, 4.x); dry run (5.2); live MN10 325/325, 0 wrong-script (5.4); OpenRouter probe returned text (3.4); 0 Roman in saved rows (5.4); text file confirmed (5.5).

## Review fixes (2026-09-28)

- [x] R.1 `runner.sh` requires uv; pip branch and `requirements.txt` removed (user: "lets get rid of pip. uv is the standard"). Settles CodeRabbit's import-check and missing-pip findings.
      → verify: `bash -n runner.sh`; `rg --hidden "requirements\.txt|pip install"` finds only the dated note in `kamma/tech.md`; `uv run pytest` green.
- [x] R.2 `runner.sh` downloads `epitaka_hi.db` only for `HINDI_REF_LANGS` targets; language prompt moved before the data step (user: "all my work will involve hindi, but the upstream that will not be the case").
      → verify: running the runner's top half with `kn` / `vi` / `hi` gives 1 / 0 / 0 Hindi entries in the download list.
- [x] R.3 A missing provider key is logged by name when the chain skips it, and a pinned `--model` with no keys stops at start-up (exit 1, no "All API keys exhausted"). Independent review, major.
      → verify: `test_missing_provider_key_is_logged_by_name`, `test_pinned_model_without_keys_stops_before_work`.
- [x] R.4 Survive no Gemini key and no OpenRouter key (user request): the default chain reaches whichever provider has keys.
      → verify: `test_default_chain_survives_missing_providers` (DeepSeek only / OpenRouter only / both).
- [x] R.5 Round-robin index counted within the provider's own keys (independent review: with 2 DeepSeek keys every Gemini call used GEMINI_KEY_1).
      → verify: `test_gemini_round_robin_is_even_with_deepseek_keys` gives g1 g2 g3 g1 g2 g3.
- [x] R.6 Key-state files store no plaintext keys (independent review).
      → verify: `test_state_file_never_holds_the_key`.
- [x] R.7 Nits: "API key(s)" log wording; dead "unless … IS Thai" clause removed; numeric HTML entities ignored by the Roman guard; stale runner comment; `uv sync --no-dev` in the runner; 401/402/403 removal tested.
      → verify: `uv run pytest` → 41 passed. Reverting R.3/R.5/R.6 and the entity fix fails 5 tests; restored → green.
