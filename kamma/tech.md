# Tech Notes

## Tools & Platforms
- Python 3 (<3.14, see below), managed with uv (`pyproject.toml` and
  `uv.lock`). uv is required: `runner.sh` has no pip fallback and
  `requirements.txt` was removed (user decision 2026-09-28: "uv is the
  standard"). Run scripts as `uv run src/book_translator.py ...`.
- Dependencies: google-genai, python-dotenv, requests, aksharamukha
  (Pāli script conversion; its `ast.Str` import caps Python below 3.14).
- Data: SQLite files in `./data/`, downloaded from the upstream
  epitaka_app GitHub releases by `runner.sh`.
- LLM providers: Gemini, DeepSeek and OpenRouter, one key rotation and one
  fallback model chain; non-Gemini models are written `provider:model`.
- Linux desktop; long runs go through `runner.sh`, usually via `just run-deepseek <lang>` (`just run` is the Claude background run)
  (DeepSeek pinned); `just next <lang>` (plus the `next-deepseek-kn` and `next-gemini-kn` shortcuts) does only the next unfinished book;
  `just export <lang>` writes everything translated so far.
- Long runs happen on a server: SSH alias `epitaka` (`root@187.126.118.33`,
  key login since 2026-10-05), repo at `/root/epitaka-translator`, code kept
  in step by `git pull`. `just pull` mirrors its `data/` here. It snapshots
  the live `epitaka_<lang>.db`/`glossary_<lang>.db` with `sqlite3 .backup`
  first, because a WAL database copied mid-write can be broken. On the server
  `uv` is not on the PATH of a non-interactive SSH command.
- 2026-10-05: before the first pull, the local DeepSeek Kannada run
  (2026-09-29 to 10-01; D-i to D-iii plus part of M-i) was kept as
  `data/*-deepseek.*` copies. The server's Claude run started over from D-i.

## Who This Is For
Me, running translations into new languages. User, 2026-09-28: "all my work
will involve hindi" — so the Hindi reference is always in play for me. Upstream
users mostly translate other languages, so Hindi-only costs (the
`epitaka_hi.db` download) must stay off their path.

## Constraints
- Paid API use (DeepSeek, OpenRouter) is fine when it gets the job done.
- API keys live only in `.env`, which is never committed and never edited by
  the agent. `.env.example` documents every new variable.
- Prompts are big (up to about 200k tokens). Every provider must accept that
  size, or the prompt must shrink for it.
- Indian-language output never contains Roman letters; Pāli terms go in the
  local script.

## Resources
- Upstream repo and data releases: github.com/dhammanana/epitaka_app.
- Hindi reference data: `epitaka_hi.zip` on the same release page.
- Real prompt/response examples in `examples/`.

## Testing
- pytest tests for new code only (for example key loading and provider
  choice), with faked API responses.
- Existing code has no tests, and this fork does not add tests for it.
- Check live behaviour with `--dry-run`, then a short `--max-parts 1` run.

## What the output looks like
- `data/epitaka_<lang>.db` (sentences, translation_remarks) and
  `data/glossary_<lang>.db`, read directly by the Epitaka app.
- Optional prompt/response logs via `--log-dir`.
- `data/costs.csv`: one line per AI call with tokens and USD, plus a printed
  running total (this call / this run / all time).
- A plain text file per sutta from `src/export_text.py`: Pāli in the target
  script, then the translation, paragraph by paragraph.
