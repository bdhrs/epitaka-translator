import sys
import time
import types

sys.argv = sys.argv[:1]  # book_translator pre-parses --lang from argv at import time
import book_translator as bt  # noqa: E402
from common import common_utils as cu  # noqa: E402


def test_stop_due_is_off_without_a_stop_time():
    assert not bt.stop_due(types.SimpleNamespace())
    assert not bt.stop_due(types.SimpleNamespace(stop_at=0))


def test_stop_due_flips_when_the_time_passes():
    now = int(time.time())
    assert not bt.stop_due(types.SimpleNamespace(stop_at=now + 600))
    assert bt.stop_due(types.SimpleNamespace(stop_at=now - 1))


def _run_main(monkeypatch, tmp_path, stop_at):
    """Run main() over books A and B with the heavy parts faked. Returns (exit code, books processed)."""
    calls = []

    def fake_process_book(book_id, **_):
        calls.append(book_id)
        return 1, 0, 0

    monkeypatch.setattr(bt, "process_book", fake_process_book)
    monkeypatch.setattr(bt, "_build_system_prompt", lambda lang: "")
    monkeypatch.setattr(bt.ai, "make_rotator", lambda keys: None)
    monkeypatch.setattr(bt.ai, "send_telegram", lambda *a, **k: None)
    monkeypatch.setattr(cu, "ensure_lang_db", lambda p: None)
    monkeypatch.setattr(cu, "ensure_glossary_db", lambda p: None)
    monkeypatch.setattr(sys, "argv", [
        "book_translator.py", "--lang", "kn", "--books", "A,B",
        "--epitaka-db", str(tmp_path / "epitaka.db"), "--stop-at", str(stop_at),
    ])
    return bt.main(), calls


def test_main_stops_before_any_book_when_the_time_has_passed(monkeypatch, tmp_path, capsys):
    code, calls = _run_main(monkeypatch, tmp_path, int(time.time()) - 1)
    assert code == 0
    assert calls == []
    assert "[STOP-AT]" in capsys.readouterr().out


def test_main_runs_every_book_when_the_time_is_far_off(monkeypatch, tmp_path, capsys):
    code, calls = _run_main(monkeypatch, tmp_path, int(time.time()) + 3600)
    assert code == 0
    assert calls == ["A", "B"]
    assert "[STOP-AT]" not in capsys.readouterr().out
