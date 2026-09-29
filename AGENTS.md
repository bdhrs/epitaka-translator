# Agent notes — epitaka translator (fork)

- uv only: `uv sync`, `uv run pytest`, `uv run src/<script>.py`. There is no pip path and no `requirements.txt`.
- Importing `src/book_translator.py` (or anything that runs `load_dotenv()`) loads the real `.env` keys. In tests and probes, delete every `*_KEY_*` env var and fake the network before calling client code — a stray call spends the user's paid keys.
- Indian-language targets must never contain Roman letters anywhere a reader sees them — translations, Pāli terms, headings and book names in exports alike: all go in the local script (`NO_ROMAN_LANGS`, `roman_bleed` in `src/book_translator.py`; `_to_script` in `src/export_text.py`).
- Run the suite as `timeout 60 uv run pytest -q`: tests stub `time.sleep`, so a regression in a retry or rate-limit loop spins forever instead of failing.
