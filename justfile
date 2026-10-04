_default:
    #!/usr/bin/env python3
    # just --list puts every setting's default between the name and the
    # description, so lines overflow; this prints name + wrapped description only.
    import json, shutil, subprocess, textwrap
    recipes = json.loads(subprocess.run(["just", "--dump", "--dump-format", "json"],
        capture_output=True, text=True, check=True).stdout)["recipes"]
    shown = {n: r["doc"] or "" for n, r in recipes.items() if not r["private"]}
    pad = max(map(len, shown)) + 2
    width = max(shutil.get_terminal_size().columns, pad + 20)
    print("Commands:\n")
    for name, doc in shown.items():
        lines = textwrap.wrap(doc, width - pad - 2) or [""]
        print(f"  {name:<{pad}}{lines[0]}")
        for line in lines[1:]:
            print(" " * (pad + 2) + line)

# Translate everything in the background: Claude, then DeepSeek while Claude's limit resets.
run lang="kn": (relay lang)

# Same as run.
relay lang="kn":
    nohup ./runner.sh {{lang}} claude:sonnet+deepseek:deepseek-v4-flash >> data/run_{{lang}}.log 2>&1 &
    @echo "Started in the background. Watch: just tail {{lang}}   Stop: just stop {{lang}}"

# Translate everything with DeepSeek only, in this window.
run-deepseek lang="kn":
    ./runner.sh {{lang}} deepseek:deepseek-v4-flash

# Translate the next unfinished book with DeepSeek, then stop.
next lang:
    ./runner.sh {{lang}} deepseek:deepseek-v4-flash next

# Translate the next unfinished Kannada book with DeepSeek, then stop.
next-deepseek-kn:
    ./runner.sh kn deepseek:deepseek-v4-flash next

# Translate the next unfinished Kannada book with Gemini, then stop.
next-gemini-kn:
    ./runner.sh kn gemini-3.8-flash next

# Translate one passage with several models, to compare them side by side.
compare-models lang="kn" book="D-i" start="971" end="978" models="gemini-3.7-flash,gemini-3.1-pro-preview,gemini-3.8-flash":
    uv run src/compare_models.py --lang {{lang}} --book {{book}} --start {{start}} --end {{end}} --models {{models}}

# Write everything translated so far into one text file.
export lang:
    uv run src/export_text.py --lang {{lang}} --out data/export_{{lang}}.txt

# Copy the server's data folder to this machine. Safe during a run.
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

# Translate everything with Claude only, in the background.
run-claude lang="kn":
    nohup ./runner.sh {{lang}} claude:sonnet >> data/run_{{lang}}.log 2>&1 &
    @echo "Started in the background. Watch: just tail {{lang}}   Stop: just stop {{lang}}"

# Watch the background run's log. Ctrl+C stops watching, not the run.
tail lang="kn":
    tail -n 50 -f data/run_{{lang}}.log

# Show progress, speed and cost per day, week or month.
stats period="day" lang="kn":
    uv run src/stats.py report {{period}} --lang {{lang}}

# Save Claude's weekly limit from /usage, e.g. just usage 9 "2026-10-10 22:30"
usage percent reset="":
    uv run src/stats.py usage {{percent}} --reset "{{reset}}"

# Stop the background run.
stop lang="kn":
    -pkill -f "[r]unner.sh {{lang}} "
    -pkill -f "[b]ook_translator.py --lang {{lang}} "
    -pkill -f "[c]laude -p --model .* --no-session-persistence .*TARGET LANGUAGE: "
    @echo "Stopped."

# Translate the next unfinished book with Claude, then stop.
next-claude lang="kn":
    ./runner.sh {{lang}} claude:sonnet next
