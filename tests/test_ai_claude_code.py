import json
import subprocess

from common import ai_claude_code


def _fake_run(body):
    def run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(body), stderr="")
    return run


def test_usage_limit_text_is_reported_as_429(monkeypatch):
    for msg in ("Claude AI usage limit reached|1760000000",
                "You've hit your limit · resets 3pm (UTC)"):
        monkeypatch.setattr(subprocess, "run", _fake_run(
            {"is_error": True, "subtype": "success", "result": msg}))
        text, status, err, _ = ai_claude_code.chat("sonnet", "", "hi", 10)
        assert text is None and status == 429 and msg[:20] in err


def test_api_status_wins_and_other_errors_keep_none(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run(
        {"is_error": True, "subtype": "success", "result": "Overloaded", "api_error_status": 529}))
    assert ai_claude_code.chat("sonnet", "", "hi", 10)[1] == 529
    monkeypatch.setattr(subprocess, "run", _fake_run(
        {"is_error": True, "subtype": "error_during_execution", "result": "boom"}))
    assert ai_claude_code.chat("sonnet", "", "hi", 10)[1] is None


def test_success_returns_text(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run(
        {"is_error": False, "result": "{}", "usage": {"input_tokens": 5, "output_tokens": 2}}))
    text, status, err, usage = ai_claude_code.chat("sonnet", "", "hi", 10)
    assert (text, status, err) == ("{}", 200, "") and usage["completion_tokens"] == 2


from datetime import datetime, timedelta, timezone

import pytest

from common import ai_client

UTC = timezone.utc
NIGHT = datetime(2026, 10, 4, 0, 40, tzinfo=UTC)  # 06:10 in Asia/Colombo


@pytest.mark.parametrize("text, now, expected", [
    # the real message from the server, 2026-10-04
    ("You've hit your session limit · resets 9:30am (Asia/Colombo)", NIGHT, datetime(2026, 10, 4, 4, 0, tzinfo=UTC)),
    ("You've hit your limit · resets 3pm (UTC)", NIGHT, datetime(2026, 10, 4, 15, 0, tzinfo=UTC)),
    # the shown time passed minutes ago: stay in the past, the caller retries soon
    ("resets 9:30am (Asia/Colombo)", datetime(2026, 10, 4, 4, 2, tzinfo=UTC), datetime(2026, 10, 4, 4, 0, tzinfo=UTC)),
    # passed hours ago: it means tomorrow
    ("resets 9:30am (Asia/Colombo)", datetime(2026, 10, 4, 6, 0, tzinfo=UTC), datetime(2026, 10, 5, 4, 0, tzinfo=UTC)),
    # the weekly screen's format
    ("resets Oct 10, 10:30pm (Asia/Colombo)", NIGHT, datetime(2026, 10, 10, 17, 0, tzinfo=UTC)),
    ("resets 12am (UTC)", datetime(2026, 10, 4, 22, 0, tzinfo=UTC), datetime(2026, 10, 5, 0, 0, tzinfo=UTC)),
    ("resets 12pm (UTC)", NIGHT, datetime(2026, 10, 4, 12, 0, tzinfo=UTC)),
    ("Claude AI usage limit reached|1760000000", NIGHT, datetime.fromtimestamp(1760000000, UTC)),
])
def test_parse_reset(text, now, expected):
    assert ai_claude_code.parse_reset(text, now) == expected


@pytest.mark.parametrize("text", ["Overloaded", "", "resets soon", "resets 9:30am (Nowhere/Land)", "resets Feb 30, 9am (UTC)"])
def test_parse_reset_gives_none_when_the_message_names_no_usable_time(text):
    assert ai_claude_code.parse_reset(text, NIGHT) is None


def test_a_session_limit_message_is_a_429_and_remembers_its_reset(monkeypatch):
    monkeypatch.setattr(ai_claude_code, "last_reset", None)
    monkeypatch.setattr(subprocess, "run", _fake_run(
        {"is_error": True, "subtype": "success",
         "result": "You've hit your session limit · resets 9:30am (Asia/Colombo)"}))
    text, status, _, _ = ai_claude_code.chat("sonnet", "", "hi", 10)
    assert text is None and status == 429
    assert ai_claude_code.last_reset is not None and ai_claude_code.last_reset.tzinfo is not None


def test_exhaustion_prints_the_reset_instant_for_the_runner(monkeypatch, capsys):
    monkeypatch.setattr(ai_client, "send_telegram", lambda m: None)
    soon = datetime.now(UTC) + timedelta(hours=2)
    monkeypatch.setattr(ai_claude_code, "last_reset", soon)
    with pytest.raises(SystemExit):
        ai_client._fatal_all_keys_exhausted()
    assert f"[RESET-AT] {int(soon.timestamp())}" in capsys.readouterr().out

    monkeypatch.setattr(ai_claude_code, "last_reset", datetime.now(UTC) - timedelta(minutes=5))
    with pytest.raises(SystemExit):
        ai_client._fatal_all_keys_exhausted()
    assert "[RESET-AT]" not in capsys.readouterr().out  # a past reset is no use to the runner
