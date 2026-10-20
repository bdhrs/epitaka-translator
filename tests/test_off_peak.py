import json
import os
import sqlite3
import sys
import time
import types
from datetime import datetime, timezone
from typing import cast

import pytest

sys.argv = sys.argv[:1]  # book_translator pre-parses --lang from argv at import time
import book_translator as bt  # noqa: E402
from common import ai_client as ai  # noqa: E402
from common import common_utils as cu  # noqa: E402


def utc(month, day, hour, minute=0, second=0):
    return datetime(2026, month, day, hour, minute, second, tzinfo=timezone.utc).timestamp()


MON_07 = utc(9, 28, 7)   # Monday 07:00 UTC, inside the 06:00-10:00 peak window
MON_10 = utc(9, 28, 10)
MON_12 = utc(9, 28, 12)  # Monday 12:00 UTC, off-peak


class Clock:
    def __init__(self, now):
        self.now = now
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        # The wait loop only ends when the clock moves, so a sleep that does not
        # move it would spin until the suite's timeout.
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture(autouse=True)
def no_real_keys(monkeypatch):
    # Importing book_translator loads the real .env, and no test here may reach a paid API.
    for k in list(os.environ):
        if "_KEY_" in k:
            monkeypatch.delenv(k)


@pytest.fixture
def clock(monkeypatch):
    c = Clock(MON_07)
    monkeypatch.setattr(bt.time, "time", c.time)
    monkeypatch.setattr(bt.time, "sleep", c.sleep)
    return c


@pytest.fixture
def local_zone(monkeypatch):
    def set_zone(name):
        monkeypatch.setenv("TZ", name)
        time.tzset()
    yield set_zone
    monkeypatch.undo()  # puts TZ back before tzset reads it
    time.tzset()


def args(model: str | None = "deepseek:deepseek-flash", dry_run=False, stop_at=0):
    return types.SimpleNamespace(model=model, dry_run=dry_run, stop_at=stop_at)


@pytest.mark.parametrize("zone", ["UTC", "Pacific/Kiritimati", "America/Los_Angeles"])
def test_deepseek_run_waits_until_off_peak_in_any_time_zone(clock, local_zone, capsys, zone):
    local_zone(zone)

    assert bt.wait_for_off_peak(args()) is True

    assert clock.now == MON_10
    assert max(clock.sleeps) <= 300
    assert sum(clock.sleeps) == MON_10 - MON_07
    out = capsys.readouterr().out
    assert out.count("[PEAK]") == 1
    assert "Waiting until 2026-09-28 10:00 UTC" in out


def test_a_start_off_the_five_minute_mark_ends_exactly_at_off_peak(clock):
    clock.now = MON_07 + 150

    assert bt.wait_for_off_peak(args()) is True

    assert clock.now == MON_10
    assert clock.sleeps[-1] == 150


def test_stop_time_ends_the_wait(clock):
    stop_at = int(MON_07) + 600

    assert bt.wait_for_off_peak(args(stop_at=stop_at)) is False

    assert clock.now == stop_at
    assert bt.stop_due(args(stop_at=stop_at))


def test_a_stop_time_inside_a_sleep_slice_ends_the_wait_on_time(clock):
    stop_at = int(MON_07) + 425

    assert bt.wait_for_off_peak(args(stop_at=stop_at)) is False

    assert clock.now == stop_at


def test_a_stop_time_already_past_returns_at_once_and_says_nothing(clock, capsys):
    assert bt.wait_for_off_peak(args(stop_at=int(MON_07) - 1)) is False

    assert clock.sleeps == []
    assert "[PEAK]" not in capsys.readouterr().out


@pytest.mark.parametrize("a", [
    args(dry_run=True),
    args(model="gemini-3.8-flash"),
    args(model="azure:DeepSeek-V4.1-Flash"),
    args(model="claude:sonnet"),
    args(model=None),
])
def test_only_a_deepseek_run_waits(clock, capsys, a):
    assert bt.wait_for_off_peak(a) is True

    assert clock.sleeps == []
    assert "[PEAK]" not in capsys.readouterr().out


def test_deepseek_run_does_not_wait_off_peak(clock, capsys):
    clock.now = MON_12

    assert bt.wait_for_off_peak(args()) is True

    assert clock.sleeps == []
    assert "[PEAK]" not in capsys.readouterr().out


PALI = {1: "alpha pali line", 2: "bravo pali line", 3: "charlie pali line"}
KANNADA = {1: "ಒಂದು", 2: "ಎರಡು", 3: "ಮೂರು"}


def translate_book(tmp_path, monkeypatch, clock, model, stop_at=0, replies=None,
                   build_seconds=0, call_seconds=0):
    """
    Run process_book on a one-paragraph book. Returns (lines saved, clock at each model call).
    `replies` is one list of line ids per model call; each context build and each call
    moves the fake clock on by the given seconds.
    """
    replies = replies or [[1, 2, 3]]
    epitaka_db = str(tmp_path / "epitaka.db")
    lang_db = str(tmp_path / "epitaka_kn.db")
    glossary_db = str(tmp_path / "glossary_kn.db")
    with sqlite3.connect(epitaka_db) as c:
        c.execute("CREATE TABLE sentences (book_id TEXT, para_id INT, line_id INT, pali TEXT)")
        c.execute("CREATE TABLE headings (book_id TEXT, para_id INT, level INT, title TEXT, chapter_len INT)")
        c.executemany("INSERT INTO sentences VALUES ('B', 1, ?, ?)", PALI.items())
    cu.ensure_lang_db(lang_db)

    class Context:
        def __init__(self, *args, **kwargs):
            self.args, self.kwargs = args, kwargs

        def build(self):
            clock.now += build_seconds
            return ""

    for name in ("PreviousTranslationContext", "MulaAtthaContext", "NissayaContext",
                 "ParallelTranslationContext", "GlossaryContextStemmed", "CommentaryContext",
                 "PaliDefsContext"):
        monkeypatch.setattr(bt, name, Context)

    call_times = []

    def fake_call(**_):
        call_times.append(clock.now)
        clock.now += call_seconds
        return json.dumps({"translations": [
            {"para_id": 1, "line_id": i, "translation": KANNADA[i], "confidence": "high"}
            for i in replies[len(call_times) - 1]
        ]})
    monkeypatch.setattr(ai, "call_ai_with_logging", fake_call)

    run_args = types.SimpleNamespace(start=1, end=-1, min_lines=50, overwrite=False, max_parts=-1,
                                     max_tokens=3000, lang="kn", dry_run=False,
                                     log_dir=str(tmp_path), model=model, stop_at=stop_at)
    saved, _, _ = bt.process_book("B", run_args, cast(ai.KeyRotator, None), epitaka_db, lang_db,
                                  glossary_db, "s", models=["m"])
    return saved, call_times


def test_chunk_is_not_sent_to_deepseek_until_off_peak(tmp_path, monkeypatch, clock):
    saved, call_times = translate_book(tmp_path, monkeypatch, clock, "deepseek:deepseek-flash")

    assert call_times == [MON_10]
    assert saved == 3


def test_no_chunk_is_sent_when_the_stop_time_falls_in_peak(tmp_path, monkeypatch, clock):
    saved, call_times = translate_book(tmp_path, monkeypatch, clock, "deepseek:deepseek-flash",
                                       stop_at=int(MON_07) + 600)

    assert call_times == []
    assert saved == 0


def test_chunk_is_sent_at_once_to_another_provider_in_peak(tmp_path, monkeypatch, clock):
    saved, call_times = translate_book(tmp_path, monkeypatch, clock, "gemini-3.8-flash")

    assert call_times == [MON_07]
    assert saved == 3


def test_a_prompt_built_across_the_start_of_peak_is_held_back(tmp_path, monkeypatch, clock):
    clock.now = utc(9, 28, 5, 59, 50)  # off-peak when the chunk starts

    saved, call_times = translate_book(tmp_path, monkeypatch, clock, "deepseek:deepseek-flash",
                                       build_seconds=5)

    assert call_times == [MON_10]
    assert saved == 3


def test_a_retry_for_missing_lines_waits_when_peak_has_started(tmp_path, monkeypatch, clock):
    first = utc(9, 28, 5, 59)
    clock.now = first

    saved, call_times = translate_book(tmp_path, monkeypatch, clock, "deepseek:deepseek-flash",
                                       replies=[[1, 2], [3]], call_seconds=120)

    assert call_times == [first, MON_10]
    assert saved == 3
