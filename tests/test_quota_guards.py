import os
import sqlite3
import sys
import types
from typing import cast

import pytest

sys.argv = sys.argv[:1]  # book_translator pre-parses --lang from argv at import time
import book_translator as bt  # noqa: E402
from common import ai_client as ai  # noqa: E402
from common import common_utils as cu  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    for k in list(os.environ):
        if "_KEY_" in k:
            monkeypatch.delenv(k)
    monkeypatch.setenv("AI_KEY_STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(ai.time, "sleep", lambda _: None)


def test_whitespace_reply_is_a_failed_try_not_a_success(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_KEY_1", "d1")
    replies = [("  \n\n", 200, ""), ("real answer", 200, "")]
    calls = []

    def chat(*a):
        calls.append(a)
        text, status, err = replies.pop(0)
        return text, status, err, {}
    monkeypatch.setattr(ai.ai_openai_compat, "chat", chat)

    text = ai.call_gemini(ai.make_rotator([]), "p", "s", models=["deepseek:deepseek-flash"])

    assert text == "real answer"
    assert len(calls) == 2


class NoContext:
    def __init__(self, *args, **kwargs):
        pass

    def build(self):
        return ""


def run_book(tmp_path, monkeypatch, limit):
    epitaka_db = str(tmp_path / "epitaka.db")
    lang_db = str(tmp_path / "epitaka_kn.db")
    glossary_db = str(tmp_path / "glossary_kn.db")
    with sqlite3.connect(epitaka_db) as c:
        c.execute("CREATE TABLE sentences (book_id TEXT, para_id INT, line_id INT, pali TEXT)")
        c.execute("CREATE TABLE headings (book_id TEXT, para_id INT, level INT, title TEXT, chapter_len INT)")
        c.execute("INSERT INTO sentences VALUES ('B', 1, 1, 'alpha pali line')")
    cu.ensure_lang_db(lang_db)
    for name in ("PreviousTranslationContext", "MulaAtthaContext", "NissayaContext",
                 "ParallelTranslationContext", "GlossaryContextStemmed", "CommentaryContext",
                 "PaliDefsContext"):
        monkeypatch.setattr(bt, name, NoContext)

    # Ten sections, each one chunk, so the abort point shows in the call count.
    one = bt.build_sections_from_headings(epitaka_db, "B", 1, -1, 50, False, lang_db)[0]
    monkeypatch.setattr(bt, "build_sections_from_headings", lambda *a, **k: [one] * 10)
    monkeypatch.setattr(bt, "merge_small_sections", lambda s: s)
    monkeypatch.setattr(bt, "MAX_CONSECUTIVE_FAILED_CHUNKS", limit)

    prompts = []

    def fake_call(**kw):
        prompts.append(kw["prompt"])
        return None  # the model gave nothing
    monkeypatch.setattr(ai, "call_ai_with_logging", fake_call)

    args = types.SimpleNamespace(start=1, end=-1, min_lines=50, overwrite=False, max_parts=-1,
                                 max_tokens=3000, lang="kn", dry_run=False,
                                 log_dir=str(tmp_path), model=None)
    bt.process_book("B", args, cast(ai.KeyRotator, None), epitaka_db, lang_db,
                    glossary_db, "s", models=["m"])
    return prompts


def test_book_stops_after_the_limit_of_failed_chunks(tmp_path, monkeypatch):
    assert len(run_book(tmp_path, monkeypatch, limit=3)) == 3

