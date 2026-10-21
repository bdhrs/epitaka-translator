import importlib
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

import verify_translation as vt
from common import ai_client as ai

ROOT = Path(__file__).resolve().parent.parent


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def utc(month, day, hour, minute=0, second=0):
    return datetime(2026, month, day, hour, minute, second, tzinfo=timezone.utc).timestamp()


MON_07 = utc(9, 28, 7)    # Monday 07:00 UTC, inside the 06:00-10:00 peak window
MON_10 = utc(9, 28, 10)
MON_12 = utc(9, 28, 12)   # Monday 12:00 UTC, off-peak


@pytest.fixture(autouse=True)
def _no_keys(monkeypatch):
    """No real API key may exist in the test environment."""
    for k in list(os.environ):
        if re.match(r"^(GEMINI|DEEPSEEK|OPENROUTER|AZURE|CLAUDE)_KEY_\d+$", k):
            monkeypatch.delenv(k, raising=False)


# ── resolve_models ────────────────────────────────────────────────────────────

def test_resolve_models_takes_one_name_or_a_comma_list():
    assert vt.resolve_models("claude:sonnet") == ["claude:sonnet"]
    assert vt.resolve_models("claude:sonnet, azure:DeepSeek-V4.1-Flash") == [
        "claude:sonnet", "azure:DeepSeek-V4.1-Flash",
    ]


def test_resolve_models_empty_is_a_fresh_copy_of_the_default_chain():
    assert vt.resolve_models("") == vt.DEFAULT_MODELS
    first = vt.resolve_models("")
    first.append("x")
    assert vt.DEFAULT_MODELS[-1] != "x"
    assert vt.resolve_models("") == vt.DEFAULT_MODELS


# ── process_chunk routing (network faked) ─────────────────────────────────────

def _make_db(path, with_translation):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE sentences "
        "(book_id TEXT, para_id INTEGER, line_id INTEGER, pali TEXT, translation TEXT)"
    )
    conn.execute(
        "INSERT INTO sentences VALUES ('B', 1, 1, 'pali line', ?)",
        (("kn line" if with_translation else None),),
    )
    conn.commit()
    conn.close()


def test_process_chunk_routes_through_ai_client_with_the_chosen_model(
        tmp_path, monkeypatch):
    epitaka_db = tmp_path / "epitaka.db"
    lang_db = tmp_path / "epitaka_kn.db"
    _make_db(epitaka_db, with_translation=False)
    _make_db(lang_db, with_translation=True)

    canned = json.dumps({"remarks": [
        {"para_id": 1, "line_id": 1, "translation": "fix", "conflict": "why", "severity": "wrong"},
    ]})
    seen = {}

    def fake_call(**kwargs):
        seen.update(kwargs)
        return canned

    monkeypatch.setattr(vt.ai, "call_ai_with_logging", fake_call)
    # Linked-text lookup is not under test here; feed it an empty context.
    monkeypatch.setattr(
        vt, "CommentaryContext",
        lambda params, book_id, lo, hi, max_chars=0: SimpleNamespace(build=lambda: ""),
    )

    params = {"epitaka_db": str(epitaka_db), "lang_db": str(lang_db),
              "glossary_db": str(tmp_path / "glossary.db")}
    saved, critical = vt.process_chunk(
        book_id="B", para_lo=1, para_hi=1, lang="kn", params=params,
        rotator=cast(ai.KeyRotator, object()), models=["claude:sonnet"],
        log_dir=str(tmp_path / "logs"), max_context_chars=100,
        apply=False, dry_run=False, chunk_tag="c1",
    )

    assert saved == 1 and critical == 0
    assert seen["model"] == "claude:sonnet"
    assert seen["models"] == ["claude:sonnet"]
    assert "Kannada" in seen["system_prompt"]

    with sqlite3.connect(lang_db) as conn:
        rows = conn.execute(
            "SELECT book_id, para_id, line_id, note, source_id FROM translation_remarks"
        ).fetchall()
    assert rows == [("B", 1, 1, "wrong", "B")]


def _review_once(tmp_path, monkeypatch, calls, reply=json.dumps({"remarks": []}), **kwargs):
    """One process_chunk call over the B fixture; `calls` counts the AI requests."""
    epitaka_db, lang_db = tmp_path / "epitaka.db", tmp_path / "epitaka_kn.db"
    if not epitaka_db.exists():
        _make_db(epitaka_db, with_translation=False)
        _make_db(lang_db, with_translation=True)
    monkeypatch.setattr(vt.ai, "call_ai_with_logging",
                        lambda **kw: calls.append(1) or reply)
    monkeypatch.setattr(
        vt, "CommentaryContext",
        lambda params, book_id, lo, hi, max_chars=0: SimpleNamespace(build=lambda: ""),
    )
    params = {"epitaka_db": str(epitaka_db), "lang_db": str(lang_db),
              "glossary_db": str(tmp_path / "glossary.db")}
    return vt.process_chunk(
        book_id="B", para_lo=1, para_hi=1, lang="kn", params=params,
        rotator=cast(ai.KeyRotator, object()), models=["claude:sonnet"],
        log_dir=str(tmp_path / "logs"), max_context_chars=100,
        apply=False, dry_run=False, chunk_tag="c1", **kwargs,
    )


def test_a_restart_skips_chunks_the_model_already_reviewed(tmp_path, monkeypatch):
    calls = []
    _review_once(tmp_path, monkeypatch, calls)
    _review_once(tmp_path, monkeypatch, calls)
    assert len(calls) == 1


def test_redo_reviews_a_finished_chunk_again(tmp_path, monkeypatch):
    calls = []
    _review_once(tmp_path, monkeypatch, calls)
    _review_once(tmp_path, monkeypatch, calls, redo=True)
    assert len(calls) == 2


def test_a_failed_call_is_not_marked_so_the_restart_retries_it(tmp_path, monkeypatch):
    calls = []
    _review_once(tmp_path, monkeypatch, calls, reply=None)
    _review_once(tmp_path, monkeypatch, calls)
    assert len(calls) == 2


def test_process_chunk_dry_run_never_calls_the_ai(tmp_path, monkeypatch):
    epitaka_db = tmp_path / "epitaka.db"
    lang_db = tmp_path / "epitaka_kn.db"
    _make_db(epitaka_db, with_translation=False)
    _make_db(lang_db, with_translation=True)

    def fail(**kwargs):
        raise AssertionError("dry-run made an AI call")

    monkeypatch.setattr(vt.ai, "call_ai_with_logging", fail)
    monkeypatch.setattr(
        vt, "CommentaryContext",
        lambda params, book_id, lo, hi, max_chars=0: SimpleNamespace(build=lambda: ""),
    )
    params = {"epitaka_db": str(epitaka_db), "lang_db": str(lang_db),
              "glossary_db": str(tmp_path / "glossary.db")}
    saved, critical = vt.process_chunk(
        book_id="B", para_lo=1, para_hi=1, lang="kn", params=params,
        rotator=cast(ai.KeyRotator, object()), models=["claude:sonnet"],
        log_dir=str(tmp_path / "logs"), max_context_chars=100,
        apply=False, dry_run=True, chunk_tag="c1",
    )
    assert (saved, critical) == (0, 0)


# ── off-peak gate ─────────────────────────────────────────────────────────────

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


@pytest.fixture
def clock(monkeypatch):
    c = Clock(MON_07)
    monkeypatch.setattr(time, "time", c.time)
    monkeypatch.setattr(time, "sleep", c.sleep)
    return c


def test_a_pinned_deepseek_review_waits_out_peak_hours(clock, capsys):
    vt._wait_for_off_peak("deepseek:deepseek-flash")

    assert clock.now == MON_10
    assert max(clock.sleeps) <= 300
    assert sum(clock.sleeps) == MON_10 - MON_07
    assert "[PEAK]" in capsys.readouterr().out


@pytest.mark.parametrize("model", [
    "claude:sonnet",
    "azure:DeepSeek-V4.1-Flash",
    "gemini-3.8-flash",
])
def test_other_providers_never_wait_even_at_peak(clock, model):
    vt._wait_for_off_peak(model)
    assert clock.sleeps == []


def test_deepseek_does_not_wait_off_peak(clock):
    clock.now = MON_12
    vt._wait_for_off_peak("deepseek:deepseek-flash")
    assert clock.sleeps == []


# ── pins ──────────────────────────────────────────────────────────────────────

def test_justfile_review_recipe_defaults_to_claude_sonnet_in_the_background():
    justfile = read("justfile")
    assert 'review lang="kn" model="claude:sonnet" *flags:' in justfile
    assert "nohup ./review_runner.sh {{lang}} {{model}} {{flags}}" in justfile
    assert ('uv run python -u src/verify_translation.py --lang "$LANG_CODE" '
            '--model "$MODEL_NAME" "$@"') in read("review_runner.sh")


def test_verify_translation_no_longer_imports_the_bai_client():
    assert "ai_client_bai" not in read("src/verify_translation.py")


def test_default_chain_stays_in_step_with_the_translator():
    # Read the translator's chain from its source text — importing
    # book_translator would run load_dotenv() into the real keys.
    m = re.search(r"FALLBACK_MODEL_CHAIN = \[(.*?)\]", read("src/book_translator.py"), re.S)
    assert m, "FALLBACK_MODEL_CHAIN not found in book_translator.py"
    chain = re.findall(r'"([^"]+)"', m.group(1))
    assert vt.DEFAULT_MODELS == chain


# ── import-time key safety ────────────────────────────────────────────────────

def test_main_dry_run_needs_no_keys(tmp_path, monkeypatch, capsys):
    epitaka_db = tmp_path / "epitaka.db"
    lang_db = tmp_path / "epitaka_kn.db"
    _make_db(epitaka_db, with_translation=False)
    _make_db(lang_db, with_translation=True)
    # No .env either: a dry run must work with zero keys configured.
    monkeypatch.setattr(vt, "load_dotenv", lambda: None)
    monkeypatch.setattr(sys, "argv", [
        "verify_translation.py", "--lang", "kn", "--book", "B",
        "--epitaka-db", str(epitaka_db), "--lang-db", str(lang_db),
        "--log-dir", str(tmp_path / "logs"), "--dry-run",
    ])
    assert vt.main() == 0
    assert "[mode] DRY RUN" in capsys.readouterr().out


def test_importing_the_module_does_not_load_dotenv(monkeypatch):
    import dotenv
    calls = []
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **kw: calls.append(1))
    try:
        importlib.reload(vt)
    finally:
        monkeypatch.undo()
        importlib.reload(vt)  # restore the real function in the module namespace
    assert calls == []
