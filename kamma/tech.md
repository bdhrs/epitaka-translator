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
  2026-10-20: `src/verify_translation.py` (translation review) also runs
  on this stack (`ai_client.py`): `--model` takes one model or a
  comma-separated list, defaulting to the translator's fallback chain.
  Its B.AI import is gone; `ai_client_bai.py` itself is untouched and
  unused. The DeepSeek off-peak gate applies to review runs too, but
  only to the first model in the list (a mid-run fallback switch is not
  visible to the script). Review findings live in `translation_remarks`,
  which is not deduped — snapshot the lang DB before re-running over the
  same book.
- Linux desktop; long runs go through `runner.sh`, usually via `just run-deepseek <lang>` (`just run` is the background relay: Claude, then DeepSeek V4.1 Flash on Azure)
  (DeepSeek pinned, waits out DeepSeek's peak hours); `just next <lang>` (plus the `next-deepseek-kn` and `next-gemini-kn` shortcuts) does only the next unfinished book;
  `just export <lang>` writes one text file per finished sutta to `exports/<lang>/`;
  `just upload <lang>` sends new ones to Google Drive as Google Docs.
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
- 2026-10-20: a run pinned to a `deepseek:` model sleeps through DeepSeek's
  peak hours (01:00-04:00 and 06:00-10:00 UTC, Monday-Friday; price page read
  2026-10-20) and carries on at off-peak, which costs half. The rule is UTC
  only. User, 2026-10-20: "the server might be running on some different time
  zone, so it needs to be universal". There is no override (the user's
  choice). The clock is checked right before every request, so a split and a
  retry wait too; a request already on its way finishes. Azure, Gemini,
  Claude, the fallback chain and `--dry-run` never wait. Chinese public
  holidays count as peak.
- 2026-10-20: the direct DeepSeek API is called as `deepseek:deepseek-flash`.
  The name has no version number and DeepSeek points it at its newest Flash
  model (change log 2026-10-17: "simply use deepseek-flash to access the latest
  model"), so it needs no update. The old `deepseek-v4-flash` is only routed
  for now (change log 2026-09-10) and is not used. User, 2026-10-20: "make
  sure that azure does not get changed. I don't think it has that latest
  model". So `azure:DeepSeek-V4.1-Flash` stays as it is: it is the deployment
  owner's name and version. `src/common/ai_client_bai.py` is a third provider
  (B.AI) with its own model names and is not touched.
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
- Existing code had no tests and this fork did not add tests for it. Since
  2026-10-20 (user: "Fix all warnings that you come across. Fix all problems.")
  a bug fix or a cleanup that touches old code gets a test too, as for
  `call_gemini_with_tools`, `_unanswered` and the parallel-translation reader.
- Check live behaviour with `--dry-run`, then a short `--max-parts 1` run.
- Type check: `[tool.pyright]` in `pyproject.toml` points Pyright at `.venv`.
  Pyright is not a dev dependency; run it from the dpd-db environment:
  `cd <repo> && /home/bodhirasa/MyFiles/3_Active/dpd-db/.venv/bin/pyright src tests`
  (0 errors on 2026-10-20). An editor must restart its Pyright to read the
  setting. The one pytest `filterwarnings` entry hides only `ast.Str is
  deprecated`, which comes from the pinned `aksharamukha 2.3`.

## What the output looks like
- `data/epitaka_<lang>.db` (sentences, translation_remarks) and
  `data/glossary_<lang>.db`, read directly by the Epitaka app.
- Optional prompt/response logs via `--log-dir`.
- `data/costs.csv`: one line per AI call with tokens and USD, plus a printed
  running total (this call / this run / all time).
- A plain text file per finished sutta from `src/export_text.py`, in
  `exports/<lang>/<lang>_<sc_id>.txt` (not in `data/`, which `just pull`
  rsyncs from the server): Pāli in the target script, then the translation,
  paragraph by paragraph. Part-done suttas are skipped.
- Proofreading (2026-10-05): `just upload` puts each file in Google Drive as a
  Google Doc, in `ePitaka Proofreading/<lang>` on the Digital Pāḷi Dictionary
  account (rclone remote `dpd_drive`). A doc is never overwritten once
  uploaded. Proofreaders fix wording in Suggesting mode and comment only on
  questions and term-wide choices; a later read-back step relies on this, and
  matches paragraphs by their Pāli line. Their rules are the doc
  `!!! README FIRST` inside each language folder (`ePitaka Proofreading/kn/`,
  the folder proofreaders get access to), so the read-back step must skip it;
  Kannada folder link (shared "Anyone with the link", Commenter):
  https://drive.google.com/drive/folders/1WFToBSZ9yISxcKTZl_xXYc-QmfiVQlpj
  its source is
  `kamma/archive/20261005_sutta_export_drive/artifacts/!!! README FIRST.txt`
  (re-upload by hand after editing it).
- The user reads Pāli and English, not Kannada (2026-10-05: "i dont read
  kannada, just know pali and english"). Proofreaders may comment in Kannada
  or English (2026-10-06: Claude reads the comments, so English is not
  required). The read-back step must show each suggestion and comment with
  the original quoted, an English translation, any doubt about the
  translation marked, and a recommendation for the user to approve.
