# Spec: Import upstream `5d463fb` — quota guards and Pāli script in prompts

## Overview

Upstream (`dhammanana/epitaka_translator`) has one commit this fork doesn't:
`5d463fb` "[Fix] script follow target, build description" (2026-10-17, ~1,300
lines, 7 files). Fork point is `a7f67a8`; fork HEAD at spec time is `226fbb4`.
The commit mixes four unrelated concerns; this thread ports three of them,
adapted to the fork's architecture, and records the fourth as a deliberate
skip. Never merge: port per the skill rules.

Upstream's headline items:
1. Empty model responses treated as failures, with a bounded retry.
2. Retry budget 10 → 3 (env-tunable).
3. Circuit breaker: abort a book after N consecutive chunks that save zero
   sentences.
4. Pāli sent to the model transliterated into the target language's own
   script (aksharamukha), with glossary keys kept Roman/IAST.
5. New `description_builder.py` (SEO descriptions + summaries, Gemini-only).

## Verified facts (2026-10-20, read from this repo)

### The user runs no Gemini calls

`book_translator.py` imports `common.ai_client as ai` (line 95), but the
fork rewrote `_generate_with_retry` into a provider dispatcher
(`ai_client.py:712-729`): the model string's prefix selects the transport —

| Prefix | Transport | Note |
|---|---|---|
| `claude` | `ai_claude_code.chat()` | Claude Code CLI |
| `deepseek`/`azure`/`openrouter` | `ai_openai_compat.chat()` | OpenAI-compatible HTTP |
| `gemini` | direct `google-genai` | present in code, **not used by the user** |

So upstream's Gemini-centric fixes must be re-shaped for the transports the
fork actually drives.

### Empty/whitespace responses — what is and isn't covered today

- `ai_openai_compat.chat` already returns `(None, …)` for empty content
  (line 82, `if not text:`), with a comment recording that DeepSeek reasoning
  mode spends the whole budget and returns empty content (lines 26-29); the
  fork disables thinking for deepseek via `EXTRA_PAYLOAD`.
- In `_generate_with_retry._call`, the non-Gemini branch raises
  `CompatError(status, err)` when `text is None` — so a truly empty reply is
  already a failed attempt, retried inside the 10-attempt budget, with an
  honest costs row. Upstream's outer empty-retry loop (`AI_MAX_EMPTY_RETRIES`)
  would be **redundant** here.
- **Gap:** the emptiness test is `if not text` — a whitespace-only reply
  (`" "`, `"\n\n"`) is truthy, passes as a *success*, flows through
  `call_gemini` → `call_ai_with_logging` → `parse_ai_json_response`, fails to
  parse there, and the chunk is skipped with lines left pending. The key
  ledger recorded a success for a call that produced nothing usable.
- `ai_claude_code.chat` can also return `""` (empty `result` from the CLI).
- The Gemini branch's `response.text` raise-on-empty risk is left untouched:
  the user runs no Gemini models (user, 2026-10-20).

### No circuit breaker exists

`book_translator.py:1333-1336`: `for chunk in chunks: u, g, r =
_handle_chunk(chunk)`. All failure paths inside `_handle_chunk` funnel to
`return 0, 0, 0` (no response line 1269, parse failure 1276, dry-run 1250,
run-ending pause 1261). A dead model/quota burns one full prompt per chunk
until the section list ends. Retry budget is hard-coded `while attempt < 10`
(`ai_client.py:662`).

**Trap to avoid:** a `0, 0, 0` return can also mean "the run is ending"
(`wait_for_off_peak` False at line 1261, `stop_due` checked in the loop).
Those must never count as chunk failures, or the breaker trips on every
normal end-of-run.

### Pāli in prompts today

- `build_prompt` (line 998) sends `s["pali"]` raw romanised IAST. No `lang`
  parameter.
- Pāli also reaches the model from `CommentaryContext` (line 812),
  `PaliDefsContext`, `MulaAtthaContext`, `NissayaContext` (its `_translit`
  converts Myanmar nissaya → IAST, the *opposite* direction), and
  `GlossaryContext`/`GlossaryContextStemmed` headwords (lines 730, 735).
- The system prompt's `no_roman_note` (line 758-762) *asks* for Pāli quotes
  in target script for `NO_ROMAN_LANGS` while showing the model Roman Pāli.
- `roman_bleed` (line 721, `NO_ROMAN_LANGS` line 714) **drops** any saved
  sentence containing a Roman letter — so a Pāli term the model leaves in
  Roman is a lost sentence on Indic targets, not just a cosmetic flaw.
- `save_glossary_terms` (`common_utils.py:487`) treats the AI's `pali` field
  as a stem and canonicalises via `resolve_pali_stem()`; it has no
  script-reverse-conversion, so a model echo in target script would fall out
  of `check_glossary_terms_for_script_bleed` as a dropped term.
- `export_text.py` already has its own smaller script map `PALI_SCRIPTS`
  (line 24) and `_to_script` with the ASCII-digits fix (decision
  2026-09-28): Aksharamukha converts digits too; exports want 0-9.

### Upstream's Pāli-script pieces (from `git show upstream/main`)

- `PALI_SCRIPT_BY_LANG` in `common_utils.py`: superset of the fork's export
  map (adds lo, km, bo, as + legacy code aliases), values are aksharamukha
  script names.
- `to_pali_script(text, lang, source="IASTPali")`: regex-protects HTML tags,
  entities, and digit tokens (`\d+(?:\.\d+)*\.?`) from conversion — the
  numbered-only-line rule and `<b>/<i>` markup must survive — `lru_cache`
  (20k) on segments, silent Roman fallback on any aksharamukha error.
- `to_roman_pali(text)`: `autodetect → IASTPali` for glossary keys.
- System-prompt block `PĀLI SCRIPT IN THIS PROMPT`: use the prompt's script
  for retained Pāli terms; the glossary `pali` field ALWAYS stays Roman/IAST
  (dictionary lookup key).
- Applied in: `build_prompt` sentences, nissaya gloss + label,
  `GlossaryContextStemmed._format_grouped`, commentary, Pāli defs, mūla
  blocks (via a `_pali_for_prompt(params, text)` helper), and
  `save_glossary_terms` key normalisation.

## Scope decisions (user, 2026-10-20)

| Upstream item | Decision |
|---|---|
| Empty-response guard | **Port, reshaped**: guard whitespace-only replies at the provider-dispatch layer; no outer empty-retry loop (redundant). Gemini branch untouched. |
| Retry budget 10 → 3 | **Knob only**: `AI_MAX_RETRIES` env var, default **10** (behaviour unchanged). The 3-attempt default is wrong for this fork's rotating pool + off-peak waits. |
| Circuit breaker | **Port, default 5** (chunks here are large; a healthy chunk never saves 0), env-overridable, dry-run exempt, run-ending skips don't count. |
| Pāli script in prompts | **Port as fork-native re-implementation** (largest task). |
| `description_builder.py` | **Skip, recorded**: Gemini-only, English-centric, output would need script conversion + bleed checks for Indic targets, and nothing in this fork consumes a `descriptions` table. Revisit when the web reader needs per-section descriptions. |
| README | Update only for what lands. |

## Constraints from project instructions

- No Roman letters in any Indian-language target a reader sees — unchanged;
  this thread *supports* it (fewer `roman_bleed` drops).
- `deepseek:deepseek-flash` name stays version-free (`tests/test_deepseek_model_name.py` pins it) — untouched by this work.
- `wait_for_off_peak` stays called in `_handle_chunk` right before the
  request — untouched position; the breaker lives in the caller loop.
- `timeout 60 uv run pytest -q` must pass; Pyright per `kamma/tech.md`
  (`<dpd-db root>/.venv/bin/pyright src tests`).
- New code gets pytest tests; old code touched by this thread gets a test
  too (tech.md policy).
- Env-var deletion + network faking in tests (AGENTS.md): never let a test
  import touch real keys or networks.

## Out of scope

- `description_builder.py` (skip recorded above and in tech.md at finalize).
- Any change to the Gemini transport branch.
- Changing the 10-attempt default retry budget.
- Export-side script handling (`export_text._to_script` behaviour is kept;
  only its map's source is unified).
