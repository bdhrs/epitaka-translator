# Translate the whole canon from the beginning with DeepSeek; resumes where it left off.
run lang:
    ./runner.sh {{lang}} deepseek:deepseek-v4-flash

# Translate only the next unfinished book with DeepSeek, then stop.
next lang:
    ./runner.sh {{lang}} deepseek:deepseek-v4-flash next

# Everything translated so far: Pāli (target script) + translation, one file.
export lang:
    uv run src/export_text.py --lang {{lang}} --out data/export_{{lang}}.txt
