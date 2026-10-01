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
