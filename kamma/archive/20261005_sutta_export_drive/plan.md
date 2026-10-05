# Plan: split export into one file per sutta, upload new ones to Google Drive

Spec: `kamma/threads/20261005_sutta_export_drive/spec.md`

## Architecture Decisions
- All export code stays in `src/export_text.py`, next to `_to_script`,
  `_paragraphs` and `export_text`. No new module.
- `export_all` (used only by `just export`) is replaced by `export_suttas`.
  The one-passage mode (`--book/--start/--end --out`, used by
  `src/compare_models.py`) is not changed.
- Sutta ranges come from the `headings` table: the first row per non-empty
  `sc_id` is the sutta heading. The range ends before the next heading with
  `level <=` the sutta's level. Paragraph-number rows (level 10, NULL
  `sc_id`) and MN subsections (level 5) never end a sutta.
- No separate title line: the sutta heading is already the first paragraph.
- Upload is a just recipe that calls rclone. There is no Python, because
  rclone already does the conversion and the skip-if-present check.
- Output goes to `exports/<lang>/`, which is ignored by git and kept out of
  `data/`, which `just pull` rsyncs from the server.

## Facts to rely on (checked 2026-10-05)
- Real heading rows `(para_id, level, title, sc_id)`, for fixtures:
  - D-i: `(3,1,'(DN) Sīlakkhandhavaggapāḷi',NULL)`,
    `(4,2,'1. Brahmajālasuttaṃ','dn1')`, `(5,4,'Paribbājakakathā','dn1')`,
    `(208,4,'Vivaṭṭakathādi','dn1')`, `(217,2,'2. Sāmaññaphalasuttaṃ','dn2')`.
    The last D-i para is 1074.
  - M-i: `(3,1,'(MN)Mūlapaṇṇāsapāḷi',NULL)`, `(4,2,'1. Mūlapariyāyavaggo',NULL)`,
    `(5,4,'1. Mūlapariyāyasuttaṃ','mn1')`, `(6,10,'1',NULL)`,
    `(55,4,'2. Sabbāsavasuttaṃ','mn2')`, `(59,5,'Dassanā pahātabbāsavā','mn2')`,
    `(95,4,'3. Dhammadāyādasuttaṃ','mn3')`, `(415,2,'2. Sīhanādavaggo',NULL)`,
    `(416,4,'1. Cūḷasīhanādasuttaṃ','mn11')`.
- `sc_id` is NULL (not '') on non-sutta rows.
- D-i/D-ii/D-iii have a translation in every Pāli paragraph. M-i is part done.
- The shortest DN sutta is dn7; its first paragraph (D-i para 692) is
  "7. Jāliyasuttaṃ".

## Phase 1 — Per-sutta export

- [x] Add `sutta_ranges(epitaka_db, book) -> list[(sc_id, start, end)]`
  in `src/export_text.py`:
  ```python
  heads = _read(epitaka_db, "SELECT para_id, level, sc_id FROM headings "
                "WHERE book_id=? ORDER BY para_id", (book,))
  seen, out = set(), []
  for i, (para, level, sc) in enumerate(heads):
      if not sc or sc in seen:
          continue
      seen.add(sc)
      end = next((p - 1 for p, lv, _ in heads[i + 1:] if lv <= level), 10**9)
      out.append((sc, para, end))
  ```
  Add tests in `tests/test_export_text.py` with the real rows above. Expect
  dn1 = (4, 216), dn2 = (217, 10**9), mn1 = (5, 54), mn2 = (55, 94), mn3
  ends at 414 (the vagga heading at 415), mn11 starts at 416. Expect para 3–4
  in no range.
  → verify: `timeout 60 uv run pytest -q tests/test_export_text.py`, all pass.
    Then change `lv <= level` to `lv < level` and confirm the range tests
    fail. Restore it in the same command.

- [x] Add `export_suttas(epitaka_db, lang, out_dir, script=None) -> (written, skipped)`.
  For every book with any translation (the `done` query from `export_all`),
  canon order:
  - For each sutta range, read the Pāli and translation paragraphs (the
    `_paragraphs` logic that `export_text` uses).
  - Finished = every Pāli paragraph with text has a translation (changed in
    review to every Pāli line holding a letter; see spec item 4). Write
    `out_dir/<lang>_<sc_id>.txt` with `export_text(...)`'s output.
  - Not finished: add `"<sc_id>: N of M paragraphs"` to the skipped list.
  - Before writing, delete `out_dir/*.txt` (only `.txt`), and create
    `out_dir` if it is missing.
  Remove `export_all` and its test. Add tests: a finished sutta is written,
  a part-done one is skipped and reported, and an old `.txt` is removed while
  a non-`.txt` file stays.
  → verify: `timeout 60 uv run pytest -q`, all pass. Revert the finished
    check (write every sutta) and confirm the skip test fails. Restore it.

- [x] Wire the CLI and just command. In `main()`, replace the no-`--book`
  path with `--out-dir`; `--out` is required only with `--book`. Print
  `Wrote N files to <dir>` plus one line per skipped sutta. Justfile:
  ```
  # Write each finished sutta to its own text file in exports/<lang>/.
  export lang:
      uv run src/export_text.py --lang {{lang}} --out-dir exports/{{lang}}
  ```
  Add `/exports` to `.gitignore`.
  → verify: `just export kn` prints 34 DN files plus the finished MN ones,
    and skipped lines for the part-done MN suttas. `ls exports/kn | wc -l`
    matches the printed count. `exports/kn/kn_dn7.txt` starts with the
    heading paragraph "7. " followed by Kannada script (ASCII digit), and
    `rg '[A-Za-z]' exports/kn` finds nothing. `git status` does not list
    `exports/`. The one-passage mode still writes its file:
    `uv run src/export_text.py --lang kn --book D-i --start 4 --end 20 --out <scratch>/t.txt`.

- [x] Phase 1 check: `timeout 60 uv run pytest -q`, all pass. Record the
  file and skipped counts in this plan.
  Result (2026-10-05): 118 passed (115 before; -1 old export_all test, +4).
  `just export kn` wrote 71 files (dn1–dn34, mn1–mn37) in ~10 s and skipped
  mn38 (4 of 100 paragraphs) and mn39–mn50 (0 of N). No Roman letters in
  `exports/kn`. DN files hold 4,534 paragraphs = 4,543 translated minus the 3
  opening paragraphs of each book. Revert checks: `lv < level` failed both
  range tests; writing every sutta failed both export_suttas tests.

## Phase 2 — Upload to Google Drive

Prerequisite: the rclone token must work. Run
`timeout 30 rclone lsd dpd_drive:`. If the remote is missing or has
no token, stop and ask the user to run
`! rclone config create dpd_drive drive scope=drive`, logged in as the
Digital Pāḷi Dictionary Google account. The login is interactive, so an
agent cannot do it. (2026-10-05: the user chose that account over the
personal `google_drive_bodhirasa:` remote, which stays untouched.)

- [x] Add the recipe:
  ```
  # Upload new sutta files to Google Drive as Google Docs. Never overwrites a doc.
  upload lang="kn" folder="ePitaka Proofreading" remote="dpd_drive":
      rclone copy exports/{{lang}} "{{remote}}:{{folder}}/{{lang}}" \
          --include "*.txt" --drive-import-formats txt \
          --drive-export-formats txt --ignore-existing -v
  ```
  Live check with one small file first, in a separate test folder:
  `rclone copy exports/kn/kn_dn7.txt "dpd_drive:ePitaka Proofreading/_probe" --drive-import-formats txt --drive-export-formats txt --ignore-existing -v`,
  run twice.
  → verify: the first run uploads one file. `rclone lsf ... _probe
    --drive-export-formats txt` shows `kn_dn7.txt`, and `rclone lsjson`
    shows mimeType `application/vnd.google-apps.document`. The second run
    transfers 0 files, and `lsf` still shows one entry (no duplicate). If the
    second run uploads again, replace `--ignore-existing` with a
    pre-listing: `rclone lsf` the folder into a scratch file, then
    `rclone copy --files-from` with only the missing names. Re-run this
    check. Tell the user the `_probe` folder exists so they can delete it.
    (Upload never deletes.)

- [x] Run `just upload kn` twice.
  Probe result (2026-10-05): one file uploaded on the first run, 0 on the
  second (`Checks: 1`), `lsf --drive-export-formats txt` shows `kn_dn7.txt`,
  and the doc downloaded as .docx has the same 19 lines as the file. No
  fallback needed. The `_probe` folder is still on Drive for the user to delete.
  Slowness (2026-10-05): the first real run sent 6 docs in ~10 min. The
  `-vv` log shows `Error 403: Quota exceeded for quota metric 'Queries' and
  limit 'Requests per minute'` for consumer project 202264815644, and the
  pacer backs off to 16 s. `dpd_drive` has no `client_id`, so it uses
  rclone's shared default ID. User chose to let it run overnight; a second
  run fills any files that failed after retries. Own client ID = possible
  follow-up.
  Fixed same evening at the user's request: own Google client ID
  (`CLIENT_ID`/`CLIENT_SECRET` in `.env`, read once, never printed) via
  `rclone authorize drive` + `rclone config update dpd_drive client_id …
  client_secret … token … --non-interactive`. Result: 63 docs in 2 min 2 s,
  0 quota errors (was 6 in ~10 min). Second `just upload kn`: 0 transferred,
  `Checks: 71 / 71`; Drive has 71 docs, local 71, no duplicate names.
  → verify: the first run lists every file in `exports/kn`. The second run
    transfers 0. The `rclone lsf` count equals `ls exports/kn | wc -l`.
    Ask the user to open `kn_dn7` in Drive and confirm it shows Kannada text
    with Pāli and translation on separate lines.

## Phase 3 — Docs and final check

- [x] Update `README.md` (the `just export` line at ~32 and the export_text
  section at ~257), `kamma/tech.md` (the "What the output looks like" export
  bullet, plus a new bullet for `just upload` and the rclone reconnect), and
  add the Suggesting-mode convention for proofreaders to `tech.md`, as the
  later read-back thread relies on it.
  → verify: `rg -n "export_kn.txt|data/export_" README.md kamma/tech.md justfile`
    finds nothing. `just` lists `export` and `upload` with their one-line
    descriptions.

- [x] Write instructions for proofreaders (user request, 2026-10-05). Draft
  shown in chat; on approval, upload as a Google Doc into `ePitaka
  Proofreading/kn/` (first placed beside `kn/`, then moved in; see below).
  Done: user asked for a tighter version named `!!! README FIRST`; source in
  this thread's `artifacts/`, uploaded 21:07 as a Google Doc next to `kn/`,
  then moved into `kn/` at the user's request (21:08: "that's what people will
  have access to"). `just upload` is unaffected: the readme is not in
  `exports/kn`, and `--ignore-existing` never deletes. Drive `kn/` now holds
  72 docs (71 suttas + readme), so a Drive-vs-local count differs by 1.
  English only (the Kannada-translation question went unanswered).
  Rules: Suggesting mode, never touch Pāli lines, keep the two-line layout,
  one suggestion per problem, never accept/reject, never rename/move docs
  (a renamed doc makes `just upload` add a fresh copy), comments in English,
  `TERM:` and `QUESTION:` prefixes, `DONE` comment when finished. Also note
  in `tech.md` that the user reads only Pāli and English, so the later
  read-back step must give English translations of each suggestion.
  → verify: `rclone lsf "dpd_drive:ePitaka Proofreading" --drive-export-formats txt`
    lists the instructions doc and `kn/`; the doc text matches the approved draft.

- [x] Final check: `timeout 60 uv run pytest -q`, all pass. `just export kn`
  run again gives the same file count. `just upload kn` transfers 0.
  Result (2026-10-05 21:06): 118 passed; `just export kn` wrote 71 files again;
  `just upload kn` transferred 0 (`Checks: 71 / 71`).
