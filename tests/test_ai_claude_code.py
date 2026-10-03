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
