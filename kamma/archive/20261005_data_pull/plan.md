# Plan: `just pull` — mirror the server's data folder

See `spec.md` in this folder for the verified facts behind every step.

## Architecture Decisions
- The whole command lives in one `justfile` recipe (bash shebang recipe). No
  new Python: the server's `sqlite3` CLI makes the clean copies, and `uv` is
  not on the PATH of a non-interactive SSH command anyway.
- Live databases are found by `glossary_<lang>.db`, not by `-wal` files,
  because the read-only `epitaka.db` also has `-wal`/`-shm` on the server.
- No `--delete` and no SSH ControlMaster: key login makes three SSH
  connections free, and local-only files must survive.
- The DeepSeek backup is a one-time step in this plan, not part of the recipe.

## Phase 1 — One-time backup of the local DeepSeek data
- [x] Copy the four local files to `-deepseek` names in `data/`. Databases via
      `sqlite3 data/epitaka_kn.db ".backup data/epitaka_kn-deepseek.db"` (same
      for `glossary_kn.db`); `cp` for `costs.csv` and `export_kn.txt`.
  → verify: `sqlite3 data/epitaka_kn-deepseek.db "select count(*) from sentences"`
    prints 15048; `sqlite3 data/glossary_kn-deepseek.db "select count(*) from glossary"`
    prints 5657; `cmp data/costs.csv data/costs-deepseek.csv` and
    `cmp data/export_kn.txt data/export_kn-deepseek.txt` are silent.

## Phase 2 — The `just pull` recipe
- [x] Add a `pull host="epitaka" dir="/root/epitaka-translator"` recipe to
      `justfile`, after `export`, with a one-line `#` description like the
      others. Body (bash shebang, `set -euo pipefail`):
      1. `live=$(ssh {{host}} '...')`: in `{{dir}}/data`, `mkdir -p .mirror`;
         for each `glossary_*.db`, derive `<lang>`; for `glossary_<lang>.db`
         and `epitaka_<lang>.db`, `if [ -f "$f" ]` then
         `sqlite3 "$f" ".backup .mirror/$f"` and `echo "$f"`. Use `if`, not
         `[ ] && ...`, so a missing file does not end the loop with a failure
         that `set -e` treats as an error.
      2. Build excludes: `*.db-wal`, `*.db-shm`, `.mirror/`, and `/<name>` per
         line of `$live`. `rsync -a --info=name1 "${ex[@]}" {{host}}:{{dir}}/data/ data/`.
      3. For each name in `$live`, `rm -f data/<name>-wal data/<name>-shm`;
         then `rsync -a --info=name1 {{host}}:{{dir}}/data/.mirror/ data/`.
  → verify: `just --list` shows `pull`; `just --dry-run pull` prints the
    script with `epitaka` and `/root/epitaka-translator` filled in.
- [x] Run `just pull` (the user approves this live run; it only reads the
      server, apart from writing `data/.mirror/` there).
  → verify: local `select count(*) from sentences` on `data/epitaka_kn.db`
    equals the server's `data/.mirror/epitaka_kn.db` count (read over SSH);
    same for `glossary`; `sqlite3 data/epitaka_kn.db "pragma integrity_check"`
    prints `ok`; `just stats` lists calls dated 2026-10-03 and later.
- [x] Run `just pull` a second time.
  → verify: rsync names only the snapshot DBs and files the run touched since
    (for example `costs.csv`, `run_kn.log`), not the reference DBs.

## Phase 3 — Docs and checks
- [x] `kamma/tech.md`: add the server (alias `epitaka`, repo path, key login)
      and `just pull` with one line on why it snapshots first. `README.md`:
      add `just pull` to the just command list (around line 26-33).
  → verify: `rg -n "just pull" kamma/tech.md README.md` shows the new lines.
- [x] Run the suite.
  → verify: `timeout 60 uv run pytest -q` passes (no code under test changed).

## Results (2026-10-05)
- Phase 1: copies hold 15,048 lines and 5,657 terms; both text copies `cmp` equal.
- First `just pull`: 81 s. Copied the two live DBs, `costs.csv`, `run_kn.log`,
  `export_kn.txt`, `logs/`, `glossary_kn.db.bak`, and six reference DBs whose
  mtimes differed (`epitaka_en/hi/my_nissaya/si/th.db`, `frequency_word.db`).
  Local 13,978 lines / 757 terms = server `.mirror/` counts; both
  `integrity_check` ok; `just stats` shows 299 calls from 2026-10-03.
- Second `just pull`: 8 s, copied only `epitaka_kn.db` and `glossary_kn.db`
  (fresh snapshots each time).
- `timeout 60 uv run pytest -q`: 115 passed, same as baseline.
- NOTICED — NOT TOUCHING: local `data/epitaka.db-wal` (0 bytes) and `-shm`
  existed from 04:30, before this thread. Cause (found in review): read-only
  opens leave them behind. The pull excludes such files.
- Both pulls ran while the server run was asleep (waiting for the Claude
  reset until 05:32), so "safe while the run writes" rests on SQLite's
  backup semantics and is not yet shown on a writing run.
- Review fixes: the server step now empties `.mirror/` first and stops on any
  failed backup (`|| exit 1`, tested with a fake failing `sqlite3`: exit 1);
  `*.tmp` excluded; `{{dir}}` quoted; README warns against pulling while
  local programs hold the DBs open. Third pull after the fixes: exit 0,
  13,978 lines / 757 terms, `quick_check` ok, `.mirror/` holds only the two
  fresh copies.
