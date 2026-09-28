# Spec: Kannada test run with a Hindi reference and DeepSeek/OpenRouter providers

## Overview
Prepare the translator for a first Kannada (`kn`) test run:

1. Use the Hindi translation DB (`epitaka_hi.db`) as a parallel reference for
   Indian target languages, in place of Thai.
2. Add DeepSeek and OpenRouter as translation providers next to Gemini, with
   numbered keys in `.env` like the Gemini keys.
3. Move the project to uv. (Review, 2026-09-28: the user dropped pip —
   "uv is the standard" — so `requirements.txt` and the pip fallback are gone.)
4. Run Kannada on MN10 (Satipaṭṭhāna Sutta, a paragraph range of `M-i`) with DeepSeek.
5. No Roman letters in Kannada output (user, 2026-09-28: "noways should there
   be any roman in kannada translation").
6. A plain text file of the result: each paragraph's Pāli in Kannada script,
   then its Kannada translation, via Aksharamukha (the user's usual tool).

Multiple Gemini keys already work (`GEMINI_KEY_<N>`, see `make_rotator` in
`src/common/ai_client.py`). No code change is needed for them; the user adds
the keys to `.env`.

## What it should do

### A. Hindi reference for Indian languages
- `runner.sh` downloads `epitaka_hi.db` from `epitaka_hi.zip`, but only when
  the target is one of `HINDI_REF_LANGS` (review, 2026-09-28: the user's own
  work always involves Hindi, upstream's mostly does not). The runner now
  asks for the language before the data step so the list can depend on it.
- `_EPITAKA_LABELS` in `src/common/context_builders.py` gets
  `"epitaka_hi.db": "Hindi translation"`.
- `src/book_translator.py` picks the parallel reference DBs per target
  language (today hard-coded `only_langs={"epitaka_en.db", "epitaka_th.db",
  "epitaka_si.db"}`, around line 1061):
  - Indian targets except Hindi (`kn ta te ml mr bn gu pa or ne`):
    English, Hindi, Sinhala.
  - Every other target, and Hindi itself: English, Thai, Sinhala (no change).
- The system prompt (`_build_system_prompt`, around lines 684–720) says
  "Devanagari does not appear in this prompt's reference material at all" and
  lists block 6 as "English/Thai/Sinhala". Both lines are built from the same
  reference-language choice, so the prompt matches what the prompt actually
  contains.
- The English fallback in the mūla/aṭṭhakathā and previous-paragraph blocks
  (`_REF_DB_FILENAME = "epitaka_en.db"`) stays as it is. Those blocks tell the
  model to reuse the wording; Hindi wording is not Kannada wording, and the
  English DB is the better-checked source.
- The script-bleed guard already treats Devanagari as foreign for `kn`, so a
  Hindi leak into Kannada output is dropped and retried. No change.

### B. DeepSeek and OpenRouter providers
Keep it small (user direction 2026-09-28: "keep it simple, dont over-engineer it").

- New module `src/common/ai_openai_compat.py`: one function
  `chat(provider, key, model, system_prompt, prompt, max_tokens, timeout)`
  that POSTs to an OpenAI-compatible `chat/completions` URL and returns
  `(text, status, error)`. URLs: DeepSeek
  `https://api.deepseek.com/chat/completions` (thinking disabled, as in
  `../dpd-db/tools/ai_openai_compat.py`), OpenRouter
  `https://openrouter.ai/api/v1/chat/completions`. Uses `requests`. No
  retries of its own — `_generate_with_retry` already retries.
- Model names take an optional provider prefix:
  `deepseek:deepseek-v4-flash`, `openrouter:stealth/space-bunny-alpha`. A bare
  name means Gemini, so existing commands keep working.
- Keys: `DEEPSEEK_KEY_<N>` and `OPENROUTER_KEY_<N>`, loaded by `make_rotator`
  next to `GEMINI_KEY_<N>`. One `KeyRotator` holds all keys and knows each
  key's provider; `acquire(model=...)` only hands out keys of that model's
  provider, and raises `AllKeysExhaustedError` at once, naming the missing
  env var, when there are none. `--api-keys` keys stay Gemini keys.
- `_generate_with_retry` sends non-Gemini models through `chat()`:
  429 → `mark_429`; 401/402/403 → `remove` (402 is DeepSeek's "insufficient
  balance"); anything else → wait and retry.
- `FALLBACK_MODEL_CHAIN` ends with `deepseek:deepseek-v4-flash` then
  `openrouter:stealth/space-bunny-alpha`.
- Fatal exhaustion still logs "All API keys exhausted" (`runner.sh` greps it).
- `.env.example` documents the new key variables. `.env` is never edited by
  the agent.
- Any provider may have no keys at all — including Gemini (user,
  2026-09-28: "the script should also survive no gemini api key! … or
  openrouter"). The fallback chain skips a keyless provider's models at once
  and logs the missing env var by name.
- Start-up check (added in review, 2026-09-28): a pinned `--model` whose
  provider has no keys stops `book_translator.py` with "set <PROVIDER>_KEY_1
  in .env" and exit 1, never the "All API keys exhausted" text that sends
  `runner.sh` into its 3 h sleep.
- Key-state files in the temp dir no longer store the key itself, only its
  env-var label and hash (review, 2026-09-28: paid keys now land there).
- Not done, on purpose: per-provider rate budgets (the translator sends one
  request at a time, about a minute each, so the Gemini default never slows
  DeepSeek), and tool calling for new providers.

### C. uv
- Add `pyproject.toml` (pinned dependencies plus a `dev` group with
  `pytest`) and `uv.lock`; delete `requirements.txt`.
- `runner.sh` requires uv: it stops with an install link when uv is missing,
  else runs `uv sync` and activates `.venv`. No pip branch.
- README: uv commands (`uv run src/book_translator.py ...`), the Hindi
  reference rule, the new providers and keys.

### E. No Roman letters in Indian-language output
Applies to the Indian targets `HINDI_REF_LANGS` plus `hi` (all written in
Indic scripts; MVP: one rule for the whole set rather than Kannada only).
- Prompt: one added line for these targets — never use Roman (Latin)
  letters; write every kept Pāli term, including the `(<i>pali term</i>)`
  quote after a defined word, in the target script.
- Guard: `check_translations_for_script_bleed` and
  `check_glossary_terms_for_script_bleed` in `src/book_translator.py` also
  flag Latin letters (ASCII `A-Za-z` plus the Latin Extended blocks used by
  IAST, e.g. ā ṃ ṭ) for these targets, after stripping HTML tags such as
  `<b>`/`<i>`, which the output must keep. Flagged items are dropped, not
  saved, and the lines stay pending for a later run — the existing handling.
  Digits and punctuation are allowed.

### F. Pāli + translation text file
User, 2026-09-28: "the final result just needs to be a text file or pdf, line
by line or para by para pali then kannada, nothing fancy".
- New script `src/export_text.py --lang kn --book M-i --start 280 --end 410
  --out <file.txt>`: reads Pāli from `epitaka.db` and translations from
  `epitaka_<lang>.db` and writes plain UTF-8 text, para by para: the
  paragraph's Pāli lines joined (converted with Aksharamukha `IASTPali` → the
  target script), a newline, the translation lines joined, a blank line.
  HTML tags are stripped. A paragraph with no translation yet gets an empty
  translation line.
- The Pāli script follows the target language (`kn` → Kannada, `te` →
  Telugu, …); `--script` overrides it with any Aksharamukha script name.
- Probe 2026-09-28 on real MN10 lines: clean output, long ಏ/ಓ for Pāli e/o,
  punctuation, brackets and § pass through, digits become Kannada digits
  (105 → ೧೦೫), a nasal before a consonant becomes ಂ (āmantesi → ಆಮಂತೇಸಿ).
  Kept as Aksharamukha's defaults, except digits: the user asked for 0-9
  (2026-09-28), so the export maps converted digits back to ASCII.

### G. Aksharamukha dependency
- Add `aksharamukha` to `pyproject.toml`. It pulls
  lxml, fonttools, regex, pyyaml, pykakasi, langcodes and requests.
- Side effect, accepted by the user: `NissayaContext._translit` in
  `src/common/context_builders.py` has always imported it inside a bare
  `except`, and the package was never installed, so the Myanmar-gloss Pāli
  words went out in Myanmar script (see `examples/`). With the package
  installed they are romanised to IAST, as the block's label already claims.
- aksharamukha 2.3 imports `ast.Str`, which Python 3.14 removes, so
  `requires-python` is capped at `<3.14` (found 2026-09-28 from a pytest
  DeprecationWarning).

### D. Tests (new code only)
`tests/` with pytest, faked HTTP responses, no network:
- Key loading per provider, and the provider filter in `acquire`.
- The `chat()` client: success, an HTTP error, and HTTP 200 with no text.
- Retry routing: 429 on DeepSeek moves to the next model; 401 removes the key.
- Reference-DB choice per target language, and the prompt lines that follow
  from it.
- The Roman-letter guard: flags `nibbāna` and `Buddha` in a `kn`
  translation, passes Kannada text with `<b>`/`<i>` tags and digits, leaves
  `vi` untouched.
- The export: a tiny fixture pair of DBs gives Kannada-script Pāli followed
  by its translation.

## Assumptions & uncertainties
- `deepseek-v4-flash` is the DeepSeek model for the run (same name as in
  dpd-db's `ai_models.json` and `ai_client_bai.py`). Its context window and
  maximum output tokens are not verified. Real prompts are 115–137 KB
  (`examples/`), about 30–35k tokens by the `len/4` estimate; responses reach
  27 KB. A probe call must confirm both limits before the live run.
- `stealth/space-bunny-alpha` is the user-named free OpenRouter model. Its
  existence, context size and free-tier daily cap are unverified; a probe of
  OpenRouter's models endpoint confirms the id.
- Probe 2026-09-28: DeepSeek (`deepseek-v4-flash`) and OpenRouter
  (`stealth/space-bunny-alpha`) both answered with `max_tokens=65536`, so no
  per-provider output cap is kept (dpd-db's 8192 was not copied). Whether
  DeepSeek silently clamps below 65536 is unknown; a truncated reply would
  show in the live run as a partial JSON salvage.
- MN10 is `M-i` paragraphs 280–410, 325 lines (user switched the test from
  `Dhp` to MN10, 2026-09-28). Para 280 is the heading "10.
  Mahāsatipaṭṭhānasuttaṃ" (this edition's title for MN10), para 410 its
  closing line.
- The Roman guard may keep a line pending forever if the model insists on a
  Roman word there. The live run's drop counts will show whether that
  happens.
- Hindi stays under the no-Roman rule (user, 2026-09-28: "indian langauges
  should never contain roman output. it should be the pali term
  transliterated into the local script"). The review measured 13.6% of the
  existing Hindi DB rows as failing the rule; a Hindi-target run will retry
  those lines, which is accepted.
- Tool calling (`call_gemini_with_tools`) stays Gemini-only. Only
  `study_builder.py` uses it; `book_translator.py` does not pass tools.
- Known gap: Marathi and Nepali share Devanagari with Hindi, so the
  script-bleed guard cannot catch a Hindi leak into those targets.

## Constraints
- Never edit `.env`. The user adds `DEEPSEEK_KEY_1` (and any others).
- Existing commands (bare Gemini model names, `--api-keys`, `runner.sh si`)
  keep working unchanged, given uv is installed.
- The user asked the agent to run the commands (2026-09-28), so the agent
  runs the probe, downloads, dry run and live runs, and reports the output.

## How we'll know it's done
- `uv run pytest` passes, and reverting each new behaviour makes its tests
  fail.
- A `--dry-run` for `kn` on MN10 writes a prompt that contains a Hindi
  reference block, no Thai block, and no "Devanagari does not appear" line.
- A live `kn` run on MN10 with `--model deepseek:deepseek-v4-flash`
  translates the whole sutta, with zero rows dropped for wrong script left
  pending at the end and no crash.
- A single probe call to `openrouter:stealth/space-bunny-alpha` returns text.
- No saved MN10 `kn` row contains a Roman letter outside HTML tags.
- The MN10 text file shows each paragraph's Kannada-script Pāli followed by
  its Kannada translation.

## What's not included
- Changing the English fallback in the mūla and previous-paragraph blocks.
- Moving `verify_translation.py` off B.AI, or giving `glossary_builder.py` /
  `study_builder.py` new providers beyond what `make_rotator` gives for free.
- Tool calling for non-Gemini providers.
- Upstream pull requests (a later thread).
