import json
import sqlite3
import sys
import types

sys.argv = sys.argv[:1]  # book_translator pre-parses --lang from argv at import time
import book_translator as bt  # noqa: E402
from common import ai_client as ai  # noqa: E402
from common import common_utils as cu  # noqa: E402

PALI = {1: "alpha pali line", 2: "bravo pali line", 3: "charlie pali line", 4: "20."}
KANNADA = {1: "ಒಂದು", 2: "ಎರಡು", 3: "ಮೂರು"}


class NoContext:
    def __init__(self, *a, **k):
        pass

    def build(self):
        return ""


def setup(tmp_path, monkeypatch, replies, id_type=int):
    """Run process_book on a one-paragraph book; `replies` is one list of line ids per model call."""
    epitaka_db = str(tmp_path / "epitaka.db")
    lang_db = str(tmp_path / "epitaka_kn.db")
    glossary_db = str(tmp_path / "glossary_kn.db")
    with sqlite3.connect(epitaka_db) as c:
        c.execute("CREATE TABLE sentences (book_id TEXT, para_id INT, line_id INT, pali TEXT)")
        c.execute("CREATE TABLE headings (book_id TEXT, para_id INT, level INT, title TEXT, chapter_len INT)")
        c.executemany("INSERT INTO sentences VALUES ('B', 1, ?, ?)", PALI.items())
    cu.ensure_lang_db(lang_db)

    for name in ("PreviousTranslationContext", "MulaAtthaContext", "NissayaContext",
                 "ParallelTranslationContext", "GlossaryContextStemmed", "CommentaryContext",
                 "PaliDefsContext"):
        monkeypatch.setattr(bt, name, NoContext)

    prompts = []

    def fake_call(**kw):
        prompts.append(kw["prompt"])
        ids = replies[len(prompts) - 1]
        return json.dumps({"translations": [
            {"para_id": id_type(1), "line_id": id_type(i), "translation": KANNADA[i], "confidence": "high"}
            for i in ids
        ]})
    monkeypatch.setattr(ai, "call_ai_with_logging", fake_call)

    args = types.SimpleNamespace(start=1, end=-1, min_lines=50, overwrite=False, max_parts=-1,
                                 max_tokens=3000, lang="kn", dry_run=False,
                                 log_dir=str(tmp_path), model=None)
    saved, _, _ = bt.process_book("B", args, None, epitaka_db, lang_db, glossary_db, "s",
                                  None, None, None, models=["m"])
    with sqlite3.connect(lang_db) as c:
        done = {r[0] for r in c.execute("SELECT line_id FROM sentences")}
    return saved, done, prompts


def test_skipped_line_is_asked_again_alone(tmp_path, monkeypatch):
    saved, done, prompts = setup(tmp_path, monkeypatch, [[1, 2], [3]])

    assert len(prompts) == 2
    assert PALI[3] in prompts[1]
    assert PALI[1] not in prompts[1] and PALI[2] not in prompts[1]
    assert done == {1, 2, 3}
    assert saved == 3


def test_line_the_model_keeps_skipping_is_asked_only_once_more(tmp_path, monkeypatch):
    saved, done, prompts = setup(tmp_path, monkeypatch, [[1, 2], []])

    assert len(prompts) == 2
    assert done == {1, 2}
    assert saved == 2


def test_number_only_line_is_never_asked_again(tmp_path, monkeypatch):
    _, _, prompts = setup(tmp_path, monkeypatch, [[1, 2, 3]])

    assert len(prompts) == 1


def test_complete_answer_needs_no_second_call(tmp_path, monkeypatch):
    _, done, prompts = setup(tmp_path, monkeypatch, [[1, 2, 3]])

    assert len(prompts) == 1
    assert done == {1, 2, 3}


def test_ids_sent_as_text_do_not_cause_a_wasted_second_call(tmp_path, monkeypatch):
    _, done, prompts = setup(tmp_path, monkeypatch, [[1, 2, 3]], id_type=str)

    assert len(prompts) == 1
    assert done == {1, 2, 3}
