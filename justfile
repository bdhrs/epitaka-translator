# Translate the whole canon from the beginning with DeepSeek; resumes where it left off.
run lang:
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

# Translate the whole canon with Claude Sonnet via the local Claude Code CLI (subscription), in the background; resumes where it left off.
run-claude lang="kn":
    nohup ./runner.sh {{lang}} claude:sonnet > data/run_{{lang}}.log 2>&1 &
    @echo "Started in the background. Watch: just tail {{lang}}   Stop: just stop {{lang}}"

# Follow the background run's log (Ctrl+C stops watching, not the run).
tail lang="kn":
    tail -n 50 -f data/run_{{lang}}.log

# Stop the background run for a language.
stop lang="kn":
    -pkill -f "[r]unner.sh {{lang}} "
    -pkill -f "[b]ook_translator.py --lang {{lang}} "
    -pkill -f "[c]laude -p --model .* --no-session-persistence .*TARGET LANGUAGE: "
    @echo "Stopped."

# Translate only the next unfinished book with Claude Sonnet via the local Claude Code CLI, then stop.
next-claude lang="kn":
    ./runner.sh {{lang}} claude:sonnet next
