## Thread
- **ID:** 20261005_sutta_export_drive
- **Objective:** Split `just export` into one file per finished sutta in `exports/<lang>/`, and upload new ones to Google Drive as Google Docs for proofreading.

## Files Changed
- `src/export_text.py` — `sutta_ranges`, `_line_ids`, `export_suttas` replace `export_all`; `--out-dir` CLI path.
- `tests/test_export_text.py` — range tests (real heading rows), finished/skip, old-file removal, line-level rule.
- `justfile` — `export` writes `exports/<lang>/`; new `upload` recipe (rclone, `dpd_drive`).
- `.gitignore` — `/exports`.
- `README.md`, `kamma/tech.md` — new export/upload behaviour, own client ID setup, proofreading conventions.
- Thread `artifacts/!!! README FIRST.txt` — proofreader rules (uploaded to Drive `kn/`).

## Findings
| # | Severity | Location | What | Why | Fix |
|---|----------|----------|------|-----|-----|
| 1 | major | `src/export_text.py` export_suttas | "Finished" was per paragraph; M-i 520 line 2 (a whole sentence) had no translation, so mn13 was exported and uploaded with a gap (CodeRabbit; validated on real data) | Proofreaders get an incomplete doc that is never overwritten | Per-line check, ignoring bare-punctuation lines ("…", "–", "+" in D-i/D-ii, which CodeRabbit's strict version would have wrongly held back) |
| 2 | minor | spec.md §3 | Closing verses / book end land in the last sutta's file | Undocumented behaviour | Spec sentence added |
| 3 | minor | spec.md, plan.md, handoff.md | Readme location and handoff state stale | Misleads the next agent | Updated |
| 4 | minor | `sutta_ranges` (future books) | Sutta headings without `sc_id` (S-v 374, A-iii, Sn) drop text silently; Ap-i/Ja-ii/Yam/Vin-v/Paṭṭh-i ranges repeat or overlap | Only matters once SN/AN/later books are translated | Deferred: recorded in spec "What's not included" for the SN/AN grouping thread |
| 5 | nit | `main()` | `--out-dir` removes every `.txt` in the given folder; `--out` with `--out-dir` silently ignored; no `main()` tests | justfile always passes `exports/<lang>` | Skipped |
| 6 | nit | `kamma/tech.md` | Points at the `kamma/archive/...` readme path, valid only after finalize | — | Finalize must archive the thread (noted in handoff) |

## Fixes Applied
- #1: `_line_ids` + per-line check; new test from real lines; skip note now "N of M lines".
- #2, #3: spec, plan, README, handoff updated.

## Test Evidence
- `timeout 60 uv run pytest -q` (whole suite) → 119 passed.
- Revert checks (one file, restored each time): paragraph-level rule and no-punctuation-exception each fail the new test; `lv < level` fails both range tests; writing every sutta fails both export tests.
- `just export kn` (all translated data) → 70 files; skips mn13 (135 of 136 lines), mn38, mn39–50. All 34 DN suttas still written.
- Subagent: `sutta_ranges` over all 57 books with `sc_id`; paragraph counts of all 71 pre-fix files vs DB → 0 mismatches; no Roman letters in `exports/kn`.
- `just upload kn` twice (pre-fix) → 63 then 0 transferred; Drive 71 docs, no duplicates.
- CodeRabbit `--agent --uncommitted --include-untracked` → 3 findings (1 major fixed, 2 minor doc fixes applied).

## Not Verified
- The user has not yet opened a doc in Drive to confirm it looks right (a probe .docx download matched the file line for line).
- Drive `kn_mn13` still has the gap; the user must delete it (upload never deletes).
- Behaviour on SN/AN/later books beyond the subagent's range measurement.

## Verdict
PASSED
- Review date: 2026-10-05
- Reviewer: Claude (implementing session) + independent subagent + CodeRabbit
