# Spec: `just pull` — mirror the server's data folder to this machine

## Overview
The translator runs on a server (SSH alias `epitaka` in `~/.ssh/config` =
`root@187.126.118.33`, repo at `/root/epitaka-translator`). The local repo
keeps its code in step with `git pull`, but its `data/` folder is out of date.
Add one `just` command, run on the local machine, that copies the server's
`data/` folder into this repo's `data/`. Then `just stats`, `just export` and
sqlite queries can be run on the server's work locally.

Login: key-based since 2026-10-05 (`ssh-copy-id` of `~/.ssh/id_ed25519.pub`).
`ssh -o BatchMode=yes epitaka` works with no password.

## Current state (verified 2026-10-05)
The local and server Kannada data are two different translations, not old
and new copies of one:

| | Local `data/` | Server `data/` |
|---|---|---|
| `epitaka_kn.db` | 15,048 lines: D-i, D-ii, D-iii complete, M-i 466 lines (DeepSeek, 2026-09-29 to 10-01) | 13,978 lines: D-i, D-ii complete, D-iii 4,470 (Claude Sonnet, from 2026-10-03) |
| `glossary_kn.db` | 5,657 terms | 757 terms |
| `costs.csv` | 259 calls, 257 DeepSeek | 299 calls from 2026-10-03, Claude |

The same line (offset 40 in D-i, D-ii, D-iii) differs in wording between the
two. The user chose (2026-10-05) a one-time backup of the local files under
`-deepseek` names; the pull then overwrites the originals.

Server (checked over SSH): `rsync` and `sqlite3` 3.45.1 are installed; `uv`
is in `~/.local/bin` and NOT on the PATH of a non-interactive SSH command;
91 GB free; `runner.sh kn claude:sonnet` is running.

## What changes on the server during a run (verified by sweep)
Swept with `rg` over `src/`, `runner.sh` and `justfile` for every file write,
then compared with the server's `ls -la data/`.

| File in `data/` | Written by | How |
|---|---|---|
| `epitaka_<lang>.db` (+ `-wal`, `-shm`) | `src/book_translator.py` | SQLite, WAL mode |
| `glossary_<lang>.db` (+ `-wal`, `-shm`) | `src/book_translator.py` | SQLite, WAL mode |
| `costs.csv` | `src/common/costs.py` | rewrite via `.csv.tmp` + rename (atomic) |
| `usage_readings.csv` | `src/stats.py` (`just usage`) | append; not on server yet |
| `run_<lang>.log` | `justfile` `run`/`relay`/`run-claude` | `nohup >>` append |
| `export_<lang>.txt` | `just export` | plain text |
| `logs/` | `--log-dir` prompt/response logs | plain text |
| `glossary_kn.db.bak` | made by hand on the server | static |
| reference DBs (`epitaka.db`, `dpd-dictionary.db`, `epitaka_en/th/si/my_nissaya/hi.db`) | `runner.sh` download | only when missing |
| `frequency_word.db` | `src/common/context_builders.py` | built only when missing |

`epitaka.db` is never written by a run: `clear_from_epitaka_db` and
`ensure_confidence_columns` in `src/book_translator.py` have no callers, and
every other connection to it only SELECTs. Its mtime is 2026-08-01 on both
sides. It does have `-wal`/`-shm` files on the server while the run reads it,
so "has a `-wal` file" does NOT mean "is being written". Gemini key state
goes to the system temp folder, outside the repo, and is not mirrored.

## Ways to do it (considered)
1. Plain `rsync` of `data/`: simplest, but a live database copied mid-write
   can be broken or miss rows still in its `-wal` file.
2. Stop the run, `rsync`, restart: safe, but interrupts the translation.
3. `scp` / `tar` over SSH: resends about 3 GB every time.
4. `sqlite3_rsync`: needs SQLite 3.47+; both ends have 3.45.1.
5. **Chosen:** the server's `sqlite3 .backup` makes a clean copy of each live
   database (safe during a run), then `rsync` pulls the rest plus those
   copies, sending only changed parts.

## What it should do
One-time, before the first pull: copy (not move) these local files, adding
`-deepseek` before the extension:
`data/epitaka_kn.db` → `data/epitaka_kn-deepseek.db`,
`data/glossary_kn.db` → `data/glossary_kn-deepseek.db`,
`data/costs.csv` → `data/costs-deepseek.csv`,
`data/export_kn.txt` → `data/export_kn-deepseek.txt`.
Copy the databases with `sqlite3 <db> ".backup <copy>"`, so nothing in a side
log is left behind. The new names cause no clash: the server step finds
languages by glossary files only on the server, and `src/compare_models.py`
only symlinks extra `*.db` files into its scratch folder.

`just pull` (variables `host="epitaka"`, `dir="/root/epitaka-translator"`):
1. One SSH command on the server: in `data/`, empty `.mirror/` (so an old
   copy can never come down), then for every `glossary_<lang>.db`,
   run `sqlite3 <db> ".backup .mirror/<db>"` for `glossary_<lang>.db` and
   `epitaka_<lang>.db` (if present). Print each name copied. Any failed
   backup ends the SSH command with exit 1, which stops the recipe.
2. `rsync -a` the server's `data/` into local `data/`. Exclude `*.db-wal`,
   `*.db-shm`, `*.tmp` (the `costs.csv` rewrite file), `.mirror/`, and the
   names printed in step 1.
3. Delete the local `-wal`/`-shm` of those names, then `rsync -a` the server's
   `data/.mirror/` into local `data/`.
4. rsync prints each file it copies.

No `--delete`: local-only files (`data/compare/`, the `-deepseek` copies)
stay. No password prompt (key login). No new Python code.

## Assumptions & uncertainties
- Assumed: a language is a translation target exactly when it has a
  `glossary_<lang>.db`. True on both sides today (only `glossary_kn.db`).
- Unknown: how much the first pull moves. `epitaka_my_nissaya.db` and
  `frequency_word.db` have different mtimes on the two sides, so rsync
  compares them in full. They may carry real differences (up to about 700 MB).
- `.mirror/` stays on the server between pulls. It is small (the size of the
  live databases).
- Do not pull while a local run or query uses the same databases.

## Constraints
- Never touch `.env`. Never mirror code (git does that).
- Never write to the server's `data/` outside `.mirror/`.

## How we'll know it's done
- After `just pull`, the line count and glossary count of local
  `data/epitaka_kn.db` / `data/glossary_kn.db` equal the server's
  `data/.mirror/` copies.
- `sqlite3 data/epitaka_kn.db "pragma integrity_check"` prints `ok`.
- `just stats` shows the server's 2026-10-03 onward calls.
- `data/epitaka_kn-deepseek.db` has 15,048 lines and
  `data/glossary_kn-deepseek.db` has 5,657 terms.
- A second `just pull` straight after the first copies almost nothing.

## What's not included
- Pushing local data to the server.
- Deleting local files that are missing on the server.
- Making stats or export read the `-deepseek` files.
- Mirroring the server's code, `.env` or temp folder.
