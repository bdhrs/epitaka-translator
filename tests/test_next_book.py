import sqlite3
import sys

sys.argv = sys.argv[:1]  # book_translator pre-parses --lang from argv at import time
import book_translator as bt  # noqa: E402
from common import common_utils as cu  # noqa: E402


def _dbs(tmp_path, source_rows, done_rows):
    epitaka_db = str(tmp_path / "epitaka.db")
    lang_db = str(tmp_path / "epitaka_kn.db")
    with sqlite3.connect(epitaka_db) as c:
        c.execute("CREATE TABLE sentences (book_id TEXT, para_id INT, line_id INT, pali TEXT)")
        c.executemany("INSERT INTO sentences VALUES (?,?,?,?)", source_rows)
    cu.ensure_lang_db(lang_db)
    with sqlite3.connect(lang_db) as c:
        c.executemany(
            "INSERT INTO sentences (book_id, para_id, line_id, translation) VALUES (?,?,?,?)",
            done_rows,
        )
    return epitaka_db, lang_db


def test_next_skips_finished_book(tmp_path, monkeypatch):
    monkeypatch.setattr(bt, "PRESET_BOOKS", "A, B, C")
    epitaka_db, lang_db = _dbs(
        tmp_path,
        [("A", 1, 1, "evaṃ me sutaṃ"), ("B", 1, 1, "ekaṃ samayaṃ"), ("C", 1, 1, "bhagavā")],
        [("A", 1, 1, "ಹೀಗೆ ನಾನು ಕೇಳಿದೆ")],
    )
    assert bt.next_unfinished_book(epitaka_db, lang_db) == "B"


def test_next_ignores_short_placeholder_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(bt, "PRESET_BOOKS", "A,B")
    epitaka_db, lang_db = _dbs(
        tmp_path,
        [("A", 1, 1, "evaṃ"), ("A", 1, 2, "1."), ("B", 1, 1, "bhagavā")],
        [("A", 1, 1, "ಹೀಗೆ")],
    )
    assert bt.next_unfinished_book(epitaka_db, lang_db) == "B"


def test_next_none_when_all_done(tmp_path, monkeypatch):
    monkeypatch.setattr(bt, "PRESET_BOOKS", "A")
    epitaka_db, lang_db = _dbs(tmp_path, [("A", 1, 1, "evaṃ")], [("A", 1, 1, "ಹೀಗೆ")])
    assert bt.next_unfinished_book(epitaka_db, lang_db) is None
