# Spec: split export into one file per sutta, upload new ones to Google Drive

## Overview
`just export <lang>` now writes every translated book into one text file,
`data/export_<lang>.txt`. Proofreading will happen in Google Docs, one doc per
sutta, in one Drive folder per language. This thread splits the export into
one file per finished sutta, in a dedicated `exports/` folder, and adds a
command that uploads the new files to Drive as Google Docs. Reading
corrections and comments back into the database is a later thread, built on a
real proofread doc.

The full loop, for context (only steps 1–2 are in this thread):
1. Export finished suttas, one file each.
2. Upload new files to the Drive folder as Google Docs. Never touch a doc
   that is already there.
3. Proofreaders fix wording in Suggesting mode and comment only on questions
   and on term choices that apply everywhere. (Manual.)
4. A person accepts or rejects suggestions in Google Docs. (Manual.)
5. A later command reads the corrected docs back, matches each paragraph to its
   Pāli line, and writes changed translations into `epitaka_<lang>.db`. It also
   lists open comments. (Later thread.)
6. Term-wide comments go into the glossary by hand, so that future
   translations follow them. (Manual.)

## What it should do
1. `just export <lang>` writes one file per finished sutta into
   `exports/<lang>/` (a new top-level folder, not `data/`), named
   `<lang>_<sc_id>.txt`, e.g. `exports/kn/kn_dn1.txt`. `sc_id` is the
   SuttaCentral-style id in the `headings` table of `data/epitaka.db`.
2. Each file has the same body format as today: each paragraph's Pāli (target
   script, ASCII digits) on one line, its translation on the next, then a
   blank line. There is no separate title line: the sutta's heading is already
   its first paragraph (e.g. D-i para 4 "1. Brahmajālasuttaṃ" has a
   translation), so a title on top would print it twice. Format is `.txt`,
   not `.md`: Markdown would merge the Pāli and translation lines, and would
   read "105. Evaṃ…" as a numbered list.
3. Where a sutta starts and ends:
   - The sutta heading is the first heading (lowest `para_id`) for each
     non-empty `sc_id` in the book. Its `level` is the sutta level.
   - The sutta runs from that heading's `para_id` up to the paragraph before
     the next heading at the same level or a higher one (a smaller or equal
     `level` number), or to the end of the book.
   - Paragraphs outside every sutta are not exported: the opening "Namo
     tassa…", the nikāya and book titles, and vagga titles (e.g. M-i para 1–4).
   - A vagga's closing summary verses and a book's closing line fall into the
     last sutta before them (e.g. M-i 412–414 in `kn_mn10.txt`, "…niṭṭhitā" in
     `kn_dn13.txt`), so they get proofread too.
4. A sutta is "finished" when every Pāli line in its range that holds a
   letter has a translation. Lines of bare punctuation ("…", "–", "+") are
   left untranslated by design and don't count. Only finished suttas are
   written. The export prints one line for each part-done sutta it skips,
   with "N of M lines". (Changed in review from per-paragraph: M-i 520 line 2,
   a whole sentence in mn13, had no translation inside a translated
   paragraph, and mn13 was exported and uploaded with that gap.) Reason:
   a doc is never overwritten once uploaded, so a part-done upload would stay
   part-done forever.
5. The export empties `exports/<lang>/` of `.txt` files before it writes, so a
   file never outlives its sutta. Nothing else in the folder is touched.
6. New `just upload <lang>` copies the files in `exports/<lang>/` to a Drive
   folder with rclone (remote `dpd_drive:`), converted to Google
   Docs. It uploads only files with no doc of the same name in the folder. It
   never overwrites, renames or deletes a doc. It prints what it uploaded.
7. `export_text.py --book … --start … --end … --out …` (the one-passage mode
   that `compare_models.py` uses) keeps working unchanged.
8. README, `kamma/tech.md` and the justfile comment describe the new behaviour.
9. `.gitignore` gets `/exports`, so exported text is never committed.
10. (Added 2026-10-05, user request.) A short instructions doc for
    proofreaders, `!!! README FIRST`, sits in `ePitaka Proofreading/kn/` —
    the folder proofreaders are given access to. The user
    reads only Pāli and English, not Kannada, so proofreaders write comments
    in English, and the later read-back step shows each suggestion with an
    English translation and a recommendation for the user to approve.

## Assumptions & uncertainties
Verified this thread (2026-10-05):
- The `headings` table has `sc_id` on sutta headings, NULL elsewhere. DN
  suttas are level 2 (dn1–dn34); MN suttas are level 4 (mn1…), their
  subsections are level 5 with the same `sc_id`, and paragraph numbers are
  level 10 with NULL `sc_id`. MN vagga titles are level 2 with NULL `sc_id`
  (e.g. M-i para 415 "2. Sīhanādavaggo"). SN/AN/Sn suttas are level 4; Dhp
  uses ranges (`dhp1-20`).
- Per-volume files would be 780k–1,175k characters. The Google Docs limit is
  about 1.02M characters, so M-i would not fit. Per-sutta DN files are
  5k–266k characters (largest dn16).
- D-i, D-ii, D-iii have a translation in every Pāli paragraph (3 single lines
  are empty, but no paragraph is). M-i is part done (1,276 of 1,796
  paragraphs).
- rclone v1.60.1 is installed. Its only remote, `google_drive_bodhirasa:`,
  is the user's personal Drive (token empty).
- 2026-10-05 change (user): the docs go to the Digital Pāḷi Dictionary
  Google account's Drive, not the personal one. A new rclone remote
  `dpd_drive` is made for it with `rclone config create dpd_drive drive
  scope=drive` (interactive browser login, run by the user). The personal
  remote is left untouched. `just upload` takes `remote="dpd_drive"`.
- rclone has `--drive-import-formats` and `--drive-export-formats`.
- Only `just export` calls `export_all`; `compare_models.py` calls the
  one-passage mode.
- `.gitignore` ignores `/data` but has no exports entry yet.
- `just pull` rsyncs the server's whole `data/` folder down (no --delete). An
  export folder inside `data/` would mix server and local exports — one more
  reason for a separate folder.

Not verified (needs a live check after the reconnect):
- `--drive-import-formats txt` turns a `.txt` into a Google Doc.
- With `--drive-export-formats txt`, rclone lists an existing doc as
  `kn_dn1.txt`, so `--ignore-existing` skips it instead of uploading a
  duplicate. If not, the recipe lists the folder first and uploads only the
  missing names.

Assumed:
- Drive folder: `ePitaka Proofreading/<lang>` (a `just upload` setting).
- AN and SN suttas would make hundreds of tiny docs (A-iv has 278). They are
  not translated yet; their grouping is a later decision.
- Paragraph matching for the later read-back uses the Pāli line, so no extra
  markers go into the docs now.
- The old `data/export_kn.txt` and `data/export_kn-deepseek.txt` are left in
  place. The user can delete them.
- The Google Doc title is the Roman file name (e.g. "kn_dn1"); the doc body
  has no Roman text. The user did not ask for a Kannada title.

## Constraints
- No Roman letters a reader sees in Indian-language output: Pāli goes
  through `_to_script`, as now.
- Export output never goes into `data/`; `data/` holds only databases, logs
  and costs.
- No new Python dependency; rclone is already installed.
- Upload never overwrites or deletes anything on Drive.
- uv only; tests run as `timeout 60 uv run pytest -q`.

## How we'll know it's done
- `just export kn` writes 34 files for DN (dn1–dn34) and the finished MN
  suttas, and prints the part-done MN suttas it skipped.
- Tests cover the sutta ranges (DN level-2, MN level-4 with level-5
  subsections and a vagga title between suttas), the finished-only rule, and
  the emptying of old files. Built from real heading rows.
- `just upload kn` run twice: the first run makes the Google Docs, and the
  second uploads nothing and makes no duplicates.
- One uploaded doc opened in Drive shows Kannada text with correct lines.

## What's not included
- Reading corrections or comments back into the database (later thread).
- Headings or styling in the docs.
- Sharing the folder with proofreaders (done by hand in Drive).
- Grouping rules for SN/AN. Known for then: a few sutta headings have no
  `sc_id` (e.g. S-v para 374 "11. Tasināsuttaṃ", one each in A-iii and Sn),
  so their text falls outside every range and is not exported or reported.
  Some later books (Ap-i, Ja-ii, Yam, Vin-v, Paṭṭh-i) have repeated or
  overlapping `sc_id` ranges. None of this touches DN or MN.
- Running on the server; the export runs locally after `just pull`.
