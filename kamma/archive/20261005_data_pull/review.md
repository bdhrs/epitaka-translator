## Thread
- **ID:** 20261005_data_pull
- **Objective:** `just pull` mirrors the server's `data/` folder into the local one, safely while the server run is going.

## Files Changed
- `justfile` — new `pull host dir` recipe: server-side `sqlite3 .backup` of live DBs into `data/.mirror/`, then two `rsync -a` pulls.
- `README.md` — `just pull` in the command list, plus a paragraph on how it works and when not to run it.
- `kamma/tech.md` — server alias, repo path, key login, why the pull snapshots first; note on the `-deepseek` copies.
- `data/*-deepseek.*` (git-ignored) — one-time copies of the local DeepSeek Kannada run.

## Findings
| # | Severity | Location | What | Why | Fix |
|---|----------|----------|------|-----|-----|
| 1 | major | `justfile` remote loop | A failed `.backup` was masked when a later one worked; the live DB was then rsynced mid-write and an old `.mirror/` copy laid over it, exit 0 | Silent stale data locally | `|| exit 1` per backup; `.mirror/` emptied at start (fixed) |
| 2 | minor | `justfile`, `README.md`, plan Results | "Safe during a run" never shown on a writing run: both pulls ran while the run slept | Results overstated | Plan Results say so (fixed); live check left open below |
| 3 | minor | `justfile` 2nd rsync | Leftovers in `.mirror/` (old copies, a killed backup's journal) came down unfiltered | Stale or mismatched files locally | Covered by emptying `.mirror/` (fixed) |
| 4 | minor | `justfile` 1st rsync | `costs.csv.tmp` can vanish mid-transfer (rsync exit 24 stops the recipe) or land half-written | Failed or dirty pull | `--exclude '*.tmp'` (fixed) |
| 5 | minor | `README.md` | No warning against pulling while local programs hold the DBs open | Writes go to the replaced copy | README sentence (fixed) |
| 6 | nit | `README.md` | "never deletes local files" is untrue (it removes `-wal`/`-shm`) | Wrong claim | Reworded (fixed) |
| 7 | nit | `justfile` | `{{dir}}` unquoted on the server | Breaks on a path with spaces | Quoted (fixed) |
| 8 | nit | `spec.md` | `frequency_word.db` listed as downloaded; it is built by `context_builders.py` | Wrong fact | Spec table fixed |

Findings 1 and 3 came from both the agent review and CodeRabbit.

## Fixes Applied
- All eight findings above.

## Test Evidence
- Remote loop with a fake `sqlite3` that fails on `epitaka_kn.db` (scope: the exact loop text, local) → exit 1, recipe would stop.
- `just pull` after fixes (scope: real server, Kannada only — the only language there) → exit 0; local 13,978 lines / 757 terms = server snapshot; `quick_check` ok; `.mirror/` holds only the two fresh copies.
- Earlier pulls: first 81 s (live DBs, logs, six reference DBs with differing mtimes), second 8 s (two live DBs only).
- `rsync` exclude anchoring checked by the reviewer with a local dry run: `/<name>` excludes only the top-level file.
- `timeout 60 uv run pytest -q` (scope: whole suite; no Python changed) → 115 passed, same as baseline.
- `-deepseek` copies: 15,048 lines, 5,657 terms (re-checked by the reviewer).

## Not Verified
- ~~A pull while the server run is actively writing.~~ Done 2026-10-05 05:36-05:39: four pulls 45 s apart during the live run, two of them within a minute after a write (DB mtime 05:38:04, 05:38:39). Every pull exit 0; local counts = server snapshot = server live DB each time (14,230 → 14,373 → 14,411 lines; 759 → 764 terms); `integrity_check` ok on both DBs every time. Note: the run closes its DB after each write, so no `-wal` file lingers on the server between writes.
- `.backup` restarting under frequent writes: only reasoned (the DBs are a few MB, so a step takes milliseconds).
- More than one target language on the server: only `kn` exists.

## Verdict
PASSED
- Review date: 2026-10-05
- Reviewer: independent Claude subagent + CodeRabbit CLI, fixes by the implementing session
