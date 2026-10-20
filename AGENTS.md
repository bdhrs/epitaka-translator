# Agent notes — epitaka translator (fork)

- uv only: `uv sync`, `uv run pytest`, `uv run src/<script>.py`. There is no pip path and no `requirements.txt`.
- Importing `src/book_translator.py` (or anything that runs `load_dotenv()`) loads the real `.env` keys. In tests and probes, delete every `*_KEY_*` env var and fake the network before calling client code — a stray call spends the user's paid keys.
- Indian-language targets must never contain Roman letters anywhere a reader sees them — translations, Pāli terms, headings and book names in exports alike: all go in the local script (`NO_ROMAN_LANGS`, `roman_bleed` in `src/book_translator.py`; `_to_script` in `src/export_text.py`).
- Run the suite as `timeout 60 uv run pytest -q`: tests stub `time.sleep`, so a regression in a retry or rate-limit loop spins forever instead of failing.
- Gemini rate limits are per Google project, not per API key, and a Google AI Pro subscription gives no API quota (ai.google.dev rate-limits and google-ai-plans pages, checked 2026-10-01): two keys from one project share one quota, so rotating them adds no headroom.
- Direct DeepSeek is called as `deepseek:deepseek-flash`, DeepSeek's version-free name for its newest Flash model: never write a version into it. Azure names and `src/common/ai_client_bai.py` (the B.AI gateway) have their own names and stay as they are (user, 2026-10-20; `tests/test_deepseek_model_name.py` pins this).
- `wait_for_off_peak` (DeepSeek peak hours, UTC only) is called in `_handle_chunk` right before the request: keep it there, not at a loop boundary. Fix every warning you meet (user, 2026-10-20); check with the Pyright command line in `kamma/tech.md`, then with the editor, which also shows 'not accessed' hints.
