# Translate the whole canon from the beginning with DeepSeek; resumes where it left off.
run lang:
    ./runner.sh {{lang}} deepseek:deepseek-v4-flash

# Everything translated so far: Pāli (target script) + translation, one file.
export lang:
    uv run src/export_text.py --lang {{lang}} --out data/export_{{lang}}.txt
