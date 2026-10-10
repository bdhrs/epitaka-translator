import sqlite3
import sys

import pytest

sys.argv = sys.argv[:1]  # book_translator pre-parses --lang from argv at import time
import book_translator as bt  # noqa: E402
from common import common_utils as cu  # noqa: E402

ALL_BOOKS = ["S-i", "Vin-i", "Dhs", "Sv-i", "Spk-i"]  # 2 mūla, Abhidhamma, aṭṭhakathā, ṭīkā


def _dbs(tmp_path, mula_done, comm_line=("Sv-i", 1, 1, "taṃ"), comm_done=()):
    """epitaka.db with a books table; the two mūla books translated iff mula_done."""
    epitaka_db = str(tmp_path / "epitaka.db")
    lang_db = str(tmp_path / "epitaka_kn.db")
    rows = [("S-i", 1, 1, "evaṃ me sutaṃ"), ("Vin-i", 1, 1, "bhagavā"),
            ("Dhs", 1, 1, "kusalo dhammo"), * (comm_line,)]
    with sqlite3.connect(epitaka_db) as c:
        c.execute("CREATE TABLE books (book_id TEXT, category TEXT, nikaya TEXT)")
        # books table columns: (book_id, category, nikaya) — category holds Mūla/Aṭṭhakathā/Ṭīkā
        for b, cat, nik in [("S-i", "Mūla", "Sutta Piṭaka"), ("Vin-i", "Mūla", "Vinaya Piṭaka"),
                            ("Dhs", "Mūla", "Abhidhamma Piṭaka"),
                            ("Sv-i", "Aṭṭhakathā", "Sutta Piṭaka"),
                            ("Spk-i", "Ṭīkā", "Sutta Piṭaka")]:
            c.execute("INSERT INTO books VALUES (?,?,?)", (b, cat, nik))
        c.execute("CREATE TABLE sentences (book_id TEXT, para_id INT, line_id INT, pali TEXT)")
        c.executemany("INSERT INTO sentences VALUES (?,?,?,?)", rows)
    cu.ensure_lang_db(lang_db)
    done = ([("S-i", 1, 1, "x"), ("Vin-i", 1, 1, "x")] if mula_done else []) + list(comm_done)
    with sqlite3.connect(lang_db) as c:
        c.executemany(
            "INSERT INTO sentences (book_id, para_id, line_id, translation) VALUES (?,?,?,?)",
            done)
    return epitaka_db, lang_db


def marker(tmp_path):
    return tmp_path / "mula_pause_kn.flag"


def test_no_pause_while_mula_work_remains(tmp_path):
    epitaka_db, lang_db = _dbs(tmp_path, mula_done=False)
    assert bt.mula_pause_due(epitaka_db, lang_db, "kn", ALL_BOOKS) is False
    assert not marker(tmp_path).exists()


def test_pauses_when_mula_complete_but_commentary_is_not(tmp_path):
    epitaka_db, lang_db = _dbs(tmp_path, mula_done=True)
    assert bt.mula_pause_due(epitaka_db, lang_db, "kn", ALL_BOOKS) is True
    assert marker(tmp_path).exists()
    assert marker(tmp_path).read_text().strip()


def test_second_run_does_not_pause_again(tmp_path):
    epitaka_db, lang_db = _dbs(tmp_path, mula_done=True)
    assert bt.mula_pause_due(epitaka_db, lang_db, "kn", ALL_BOOKS) is True
    # re-run, marker present: continue with everything
    assert bt.mula_pause_due(epitaka_db, lang_db, "kn", ALL_BOOKS) is False


def test_no_pause_when_commentary_already_started(tmp_path):
    # a language already past the root texts must not waste a run on the pause
    epitaka_db, lang_db = _dbs(tmp_path, mula_done=True,
                               comm_done=[("Sv-i", 1, 1, "ಅದನ್ನು")])
    assert bt.commentary_started(epitaka_db, lang_db, ALL_BOOKS) is True
    assert bt.mula_pause_due(epitaka_db, lang_db, "kn", ALL_BOOKS) is False
    assert not marker(tmp_path).exists()


def test_no_pause_without_a_books_table(tmp_path):
    # tiny DBs with no books table: the gate stays out of the way
    epitaka_db, lang_db = _dbs(tmp_path, mula_done=True)
    sqlite3.connect(epitaka_db).execute("DROP TABLE books")
    assert bt.sutta_vinaya_mula_books(epitaka_db) == set()
    assert bt.mula_pause_due(epitaka_db, lang_db, "kn", ALL_BOOKS) is False


def test_lift_writes_marker_when_this_run_finished_the_mula(tmp_path):
    epitaka_db, lang_db = _dbs(tmp_path, mula_done=True)
    assert bt.lift_mula_pause_if_done(epitaka_db, lang_db, "kn", ALL_BOOKS) is True
    assert marker(tmp_path).exists()


def test_no_lift_while_mula_work_remains(tmp_path):
    epitaka_db, lang_db = _dbs(tmp_path, mula_done=False)
    assert bt.lift_mula_pause_if_done(epitaka_db, lang_db, "kn", ALL_BOOKS) is False
    assert not marker(tmp_path).exists()


def test_next_picks_abhidhamma_mula_after_sutta_vinaya_mula_done(tmp_path):
    # Dhs (Abhidhamma Mūla) precedes the commentaries in preset order
    saved = bt.PRESET_BOOKS
    bt.PRESET_BOOKS = "S-i, Vin-i, Dhs, Sv-i, Spk-i"
    try:
        epitaka_db, lang_db = _dbs(tmp_path, mula_done=True)
        assert bt.next_unfinished_book(epitaka_db, lang_db) == "Dhs"
    finally:
        bt.PRESET_BOOKS = saved


# ── main() ────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _no_keys_no_network(monkeypatch):
    """No real API key may exist and no call may leave the process."""
    import re
    import os
    for k in list(os.environ):
        if re.match(r"^(GEMINI|DEEPSEEK|OPENROUTER|AZURE|CLAUDE)_KEY_\d+$", k):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(bt.ai, "send_telegram", lambda *a, **kw: None)


def _run_main(monkeypatch, tmp_path, epitaka_db, books="preset", extra=()):
    argv = ["book_translator.py", "--lang", "kn", "--books", books,
            "--epitaka-db", epitaka_db, "--log-dir", str(tmp_path / "logs"), *extra]
    monkeypatch.setattr(sys, "argv", argv)
    return bt.main()


def test_main_preset_pauses_when_mula_complete(tmp_path, monkeypatch, capsys):
    epitaka_db, lang_db = _dbs(tmp_path, mula_done=True)
    assert _run_main(monkeypatch, tmp_path, epitaka_db) == 0
    out = capsys.readouterr().out
    assert "natural pause" in out
    assert marker(tmp_path).exists()


def test_main_preset_limits_itself_to_mula_books_and_lifts_the_pause(
        tmp_path, monkeypatch, capsys):
    epitaka_db, lang_db = _dbs(tmp_path, mula_done=False)
    processed = []

    def fake_process_book(**kwargs):
        book_id = kwargs["book_id"]
        processed.append(book_id)
        # pretend this book got fully translated
        with sqlite3.connect(lang_db) as c:
            for b, p, l in sqlite3.connect(epitaka_db).execute(
                    "SELECT book_id, para_id, line_id FROM sentences WHERE book_id=?", (book_id,)):
                c.execute("INSERT OR REPLACE INTO sentences (book_id, para_id, line_id, translation) "
                          "VALUES (?,?,?,?)", (b, p, l, "x"))
        return 1, 0, 0

    monkeypatch.setattr(bt, "process_book", fake_process_book)
    monkeypatch.setattr(bt.ai, "make_rotator", lambda keys: object())
    assert _run_main(monkeypatch, tmp_path, epitaka_db) == 0
    out = capsys.readouterr().out
    assert processed == ["S-i", "Vin-i"]  # only Sutta/Vinaya Mūla books, nothing past them
    assert "Mūla phase" in out
    assert "natural pause" in out  # the pause was lifted in this same run
    assert marker(tmp_path).exists()


def _stub_run(monkeypatch):
    monkeypatch.setattr(bt, "process_book", lambda **kw: (0, 0, 0))
    monkeypatch.setattr(bt.ai, "make_rotator", lambda keys: object())


def test_dry_run_does_not_use_up_the_pause(tmp_path, monkeypatch, capsys):
    epitaka_db, lang_db = _dbs(tmp_path, mula_done=True)
    _stub_run(monkeypatch)
    assert _run_main(monkeypatch, tmp_path, epitaka_db, books="preset", extra=["--dry-run"]) == 0
    assert "natural pause" in capsys.readouterr().out
    assert not marker(tmp_path).exists()  # the real run after it must still pause


def test_dry_run_next_does_not_use_up_the_pause(tmp_path, monkeypatch):
    epitaka_db, lang_db = _dbs(tmp_path, mula_done=True)
    _stub_run(monkeypatch)
    assert _run_main(monkeypatch, tmp_path, epitaka_db, books="next", extra=["--dry-run"]) == 0
    assert not marker(tmp_path).exists()


def test_explicit_book_run_does_not_lift_the_pause(tmp_path, monkeypatch):
    epitaka_db, lang_db = _dbs(tmp_path, mula_done=True)
    _stub_run(monkeypatch)
    assert _run_main(monkeypatch, tmp_path, epitaka_db, books="Vin-i") == 0
    assert not marker(tmp_path).exists()


def test_abhidhamma_translation_is_not_commentary(tmp_path):
    epitaka_db, lang_db = _dbs(tmp_path, mula_done=True, comm_done=[("Dhs", 1, 1, "x")])
    assert bt.commentary_started(epitaka_db, lang_db, ALL_BOOKS) is False
    assert bt.mula_pause_due(epitaka_db, lang_db, "kn", ALL_BOOKS) is True
