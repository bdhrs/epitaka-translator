_default:
    @just --list

# Translate the whole canon in the background: Claude until its limit, DeepSeek until Claude resets, then Claude again (same as relay).
run lang="kn": (relay lang)

# Same as run, written out: Claude, then DeepSeek while Claude waits for its reset. Resumes where it left off.
relay lang="kn":
    nohup ./runner.sh {{lang}} claude:sonnet+deepseek:deepseek-v4-flash >> data/run_{{lang}}.log 2>&1 &
    @echo "Started in the background. Watch: just tail {{lang}}   Stop: just stop {{lang}}"

# Translate the whole canon from the beginning with DeepSeek, in the foreground; resumes where it left off.
run-deepseek lang="kn":
    ./runner.sh {{lang}} deepseek:deepseek-v4-flash

# Translate only the next unfinished book with DeepSeek, then stop.
next lang:
    ./runner.sh {{lang}} deepseek:deepseek-v4-flash next

# Translate only the next unfinished book into Kannada with DeepSeek, then stop.
next-deepseek-kn:
    ./runner.sh kn deepseek:deepseek-v4-flash next

# Translate only the next unfinished book into Kannada with Gemini, rotating through the Gemini keys.
next-gemini-kn:
    ./runner.sh kn gemini-3.8-flash next

# Run one section of a book through several models and export each result to data/compare/ for reading side by side.
compare-models lang="kn" book="D-i" start="971" end="978" models="gemini-3.7-flash,gemini-3.1-pro-preview,gemini-3.8-flash":
    uv run src/compare_models.py --lang {{lang}} --book {{book}} --start {{start}} --end {{end}} --models {{models}}

# Everything translated so far: Pāli (target script) + translation, one file.
export lang:
    uv run src/export_text.py --lang {{lang}} --out data/export_{{lang}}.txt

# Copy the server's data folder here (overwrites local copies); safe while the server run is going.
pull host="epitaka" dir="/root/epitaka-translator":
    #!/usr/bin/env bash
    set -euo pipefail
    # A live database copied mid-write can be broken, so the server first makes
    # clean copies of the ones the run writes (each target language has a glossary).
    # .mirror is emptied first so a copy left by an earlier pull can never come down.
    live=$(ssh {{host}} 'cd "{{dir}}/data" && rm -rf .mirror && mkdir .mirror && for g in glossary_*.db; do
        l=${g#glossary_}; l=${l%.db}
        for f in "epitaka_$l.db" "$g"; do
            if [ -f "$f" ]; then sqlite3 "$f" ".backup .mirror/$f" || exit 1; echo "$f"; fi
        done
    done')
    # costs.csv is rewritten through a .tmp file that can vanish mid-transfer.
    ex=(--exclude '*.db-wal' --exclude '*.db-shm' --exclude '*.tmp' --exclude '.mirror/')
    for n in $live; do ex+=(--exclude "/$n"); done
    rsync -a --info=name1 "${ex[@]}" "{{host}}:{{dir}}/data/" data/
    # A stale local side log would be replayed onto the new copy.
    for n in $live; do rm -f "data/$n-wal" "data/$n-shm"; done
    rsync -a --info=name1 "{{host}}:{{dir}}/data/.mirror/" data/

# Translate the whole canon with Claude Sonnet via the local Claude Code CLI (subscription), in the background; resumes where it left off.
run-claude lang="kn":
    nohup ./runner.sh {{lang}} claude:sonnet >> data/run_{{lang}}.log 2>&1 &
    @echo "Started in the background. Watch: just tail {{lang}}   Stop: just stop {{lang}}"

# Follow the background run's log (Ctrl+C stops watching, not the run).
tail lang="kn":
    tail -n 50 -f data/run_{{lang}}.log

# Stats from the call log, per day, week or month: lines, work time, lines per hour, cost, recent sessions, and what is left.
stats period="day" lang="kn":
    uv run src/stats.py report {{period}} --lang {{lang}}

# Save a Claude weekly-limit reading (the percent shown by /usage). Example: just usage 9 "2026-10-10 22:30"
usage percent reset="":
    uv run src/stats.py usage {{percent}} --reset "{{reset}}"

# Stop the background run for a language.
stop lang="kn":
    -pkill -f "[r]unner.sh {{lang}} "
    -pkill -f "[b]ook_translator.py --lang {{lang}} "
    -pkill -f "[c]laude -p --model .* --no-session-persistence .*TARGET LANGUAGE: "
    @echo "Stopped."

# Translate only the next unfinished book with Claude Sonnet via the local Claude Code CLI, then stop.
next-claude lang="kn":
    ./runner.sh {{lang}} claude:sonnet next
