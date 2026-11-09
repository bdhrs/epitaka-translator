# Plan: Import upstream `5d463fb` — quota guards and Pāli script in prompts

See `spec.md` in this folder for the verified facts and scope decisions.

Upstream reference: `dhammanana/epitaka_translator` `5d463fb`
(2026-10-17); fork point `a7f67a8`. Port, never merge.

## Outcome (2026-11-09)

Legend: `[x]` done, `[-]` dropped by decision.

- Phase 1 shipped without the `AI_MAX_RETRIES` knob (user: minimum that works, default stays 10).
- Phase 2 shipped with Lao, Khmer, Tibetan and Assamese added; legacy aliases left out. A broken conversion falls back to Roman and warns once. Exports for the four new languages now convert (user only exports Kannada and Telugu, so no change needed).
- Phase 3 dropped: run logs show 221 of 247,829 Kannada and 176 of 251,796 Telugu sentences dropped for Roman letters (about 0.08 percent), and dropped lines are retried on later runs.
- Phase 4: README, `kamma/tech.md` and `.env.example` updated; a local `import-upstream` skill with a decision log was added under `.agents/skills`.
- The Phase 2 round-trip check in `tests/test_pali_script.py` covers three words, not a sample.

## Architecture Decisions

- **Whitespace guard at the dispatch layer, not an outer retry loop.** The
  fork's compat transports already turn empty replies into `CompatError`
  (retried, honestly costed). Only whitespace-only text slips through as a
  false success, so the fix is one strictness change where the transport
  text is checked (`_generate_with_retry._call`, non-Gemini branch), not
  upstream's `AI_MAX_EMPTY_RETRIES` loop around `call_gemini`.
- **Circuit breaker counts only genuine model failures.** `_handle_chunk`
  returns `0, 0, 0` both for failures and for "run is ending"
  (`wait_for_off_peak` False). The breaker must not count the latter — check
  `stop_due(args)`/pause state before counting a zero.
- **One script map, two consumers.** `PALI_SCRIPT_BY_LANG` lives in
  `common_utils.py`; `export_text.PALI_SCRIPTS` becomes a view onto it.
  Prompt-side conversion uses upstream's protection regex (tags, entities,
  digit tokens stay unconverted); the 2026-09-28 ASCII-digits decision stays
  export-side only.
- **Glossary keys re-Romanised at save time.** `save_glossary_terms` runs
  `to_roman_pali()` on the AI's `pali` field before `resolve_pali_stem()`,
  so target-script echoes survive `check_glossary_terms_for_script_bleed`
  instead of being dropped.
- **`no_roman_note` is generalised, not duplicated.** The system prompt gets
  upstream's `PĀLI SCRIPT IN THIS PROMPT` block (script targets: quote Pāli
  in that script, glossary field always Roman; Roman-fallback targets: keep
  the existing wording). `roman_bleed` enforcement is untouched.

## Phase 1 — Quota guards (`ai_client.py`, `book_translator.py`)

- [x] Strict whitespace check on transport text. In
      `_generate_with_retry._call`'s non-Gemini branch, change the failure
      condition from `text is None` to `text is None or not text.strip()`
      (covers `ai_openai_compat` and `ai_claude_code` in one place, keeps the
      `CompatError` retry/cost path). Gemini branch untouched.
  → verify: new test in `tests/` (env vars scrubbed per conftest): stub
    `ai_openai_compat.chat` to return `"   "` once then a real sentence;
    assert the call succeeds on the second attempt and `costs.record` saw an
    error row for the first; and that `"   "` on every attempt ends in
    `(None, None, None)`.
- [-] `AI_MAX_RETRIES` knob: `MAX_RETRY_ATTEMPTS = int(os.environ.get(
      "AI_MAX_RETRIES", "10"))` in `ai_client.py`, used in
      `_generate_with_retry`'s `while attempt < …`. Default behaviour
      unchanged; docstring/comment updated (the "retry up to 10 attempts"
      doc lines).
  → verify: test sets `AI_MAX_RETRIES=1` with a stubbed transport that always
    raises `CompatError`; assert exactly one transport call.
- [x] Circuit breaker in `book_translator.py`: module constant
      `MAX_CONSECUTIVE_FAILED_CHUNKS = int(os.environ.get(
      "MAX_CONSECUTIVE_FAILED_CHUNKS", "5"))` near the other tuning knobs;
      counter reset per book; in the `for chunk in chunks:` loop, on
      `u == 0` and **not** `args.dry_run` and **not** `stop_due(args)`
      (and the off-peak pause not just ending the run), increment; at the
      limit print an `[abort]` line (upstream's wording) and break the chunk
      loop and the section loop. Any `u > 0` resets the counter.
  → verify: new test: stub the AI call to return `None` every time; run
    `process_book`-level flow with a small fake DB (pattern of
    `tests/test_missing_lines.py`) and assert the loop stops after
    `MAX_CONSECUTIVE_FAILED_CHUNKS` calls, not per section list; second test:
    with `stop_due` tripping, the counter never fires.
- [x] Run the suite.
  → verify: `timeout 60 uv run pytest -q` passes;
    `<dpd-db root>/.venv/bin/pyright src tests`
    clean for touched files.

## Phase 2 — Shared Pāli-script plumbing (`common_utils.py`, `export_text.py`)

- [x] Port into `common_utils.py`: `PALI_SCRIPT_BY_LANG` (upstream's full
      map incl. legacy aliases), `pali_script_name()`, `to_pali_script()`
      (upstream's `_PROTECTED_RE` tag/entity/digit protection,
      `lru_cache(20_000)` segment cache, `IASTPali` source default, silent
      Roman fallback), `to_roman_pali()` (`autodetect → IASTPali`).
  → verify: new `tests/test_pali_script.py`: `<b>bhikkhu</b>` keeps its tag;
    `2933.` stays Roman; `bhikkhu` → Devanagari for `hi`, Sinhala for `si`,
    unchanged for `en`; broken aksharamukha import falls back to input;
    round-trip `to_roman_pali(to_pali_script(x, "hi")) == x` for a sample.
- [x] `export_text.py`: replace the literal `PALI_SCRIPTS` dict with a
      derivation from `cu.PALI_SCRIPT_BY_LANG` (keep only the keys the
      exporter had, so export behaviour is unchanged); `_to_script`,
      `_ascii_digits` untouched.
  → verify: existing `tests/test_export_text.py` passes unchanged; new assert
    that the derived map equals the old literal dict.
- [x] Run the suite.
  → verify: `timeout 60 uv run pytest -q` passes.

## Phase 3 — Pāli script into the prompt path

- [-] `context_builders.py`: add `_pali_for_prompt(params, text)`; apply it
      where Pāli is emitted: `CommentaryContext`, `PaliDefsContext`,
      `MulaAtthaContext`, `GlossaryContext` and
      `GlossaryContextStemmed._format_grouped` (headword display only —
      lookup keys stay Roman), and `NissayaContext` (label names the script;
      `_translit` gains the script-target branch
      `to_pali_script(text, lang, source="autodetect")`, keeping the IAST
      path for Roman targets).
  → verify: new tests with `params={"lang": "hi", …}` and stubbed DB rows:
    each block's output contains Devanagari Pāli; with `lang="en"` output is
    byte-identical to today's.
- [-] `book_translator.py`: `build_prompt(..., lang: str = "")`; sentences
      use `cu.to_pali_script(s["pali"] or "", lang)`; the `_build` closure
      in `_handle_chunk` passes `lang=args.lang`.
  → verify: test calls `build_prompt` with a small chunk, `lang="hi"`:
    the flat sentence list's `pali` values are Devanagari; `lang=""`
    (default) leaves them Roman.
- [-] System prompt: replace `no_roman_note` with the script-aware block —
      script targets get upstream's `PĀLI SCRIPT IN THIS PROMPT` text
      (quote Pāli in the prompt's script; glossary `pali` field ALWAYS
      Roman/IAST + the matching bullet in the glossary rules section);
      Roman-fallback targets keep the current keep-Pāli-Roman wording.
  → verify: test asserts `_build_system_prompt("hi")` contains the script
    block and the Roman-glossary rule, and `_build_system_prompt("en")`
    matches the old text modulo the new block.
- [-] `save_glossary_terms` (`common_utils.py`): normalise the AI's `pali`
      field with `to_roman_pali()` before stem resolution/skip-term checks;
      log a debug line when a key was converted.
  → verify: test: a term with Devanagari `pali` is saved with its Roman key
    (query the stub DB); `tests/test_*` glossary tests still pass.
- [-] Run the suite.
  → verify: `timeout 60 uv run pytest -q` passes; Pyright clean.

## Phase 4 — Docs and close

- [x] README: add a short "Pāli script in prompts" subsection (fork wording:
      NO_ROMAN_LANGS framing, map location, glossary-stays-Roman rule) and
      mention `MAX_CONSECUTIVE_FAILED_CHUNKS` / `AI_MAX_RETRIES` in the run
      options list.
  → verify: `rg -n "AI_MAX_RETRIES|MAX_CONSECUTIVE_FAILED_CHUNKS|Pāli script" README.md` hits.
- [x] `kamma/tech.md`: dated note that upstream `5d463fb` was studied;
      `description_builder.py` deliberately skipped (Gemini-only,
      English-centric, no consumer here — revisit when the web reader needs
      per-section descriptions); retry default stays 10 by decision.
  → verify: `rg -n "5d463fb|description_builder" kamma/tech.md` hits.
- [x] Full suite + type check.
  → verify: `timeout 60 uv run pytest -q` green;
    `pyright src tests` clean; `git diff --stat` reviewed for stray files.
