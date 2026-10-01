import csv
import types
from datetime import datetime, timezone

import pytest

from common import ai_client as ai
from common import costs

MON_PEAK = datetime(2026, 9, 28, 7, 0, tzinfo=timezone.utc)     # Monday 07:00 UTC
MON_OFFPEAK = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)  # Monday 12:00 UTC
SAT_MORNING = datetime(2026, 10, 3, 7, 0, tzinfo=timezone.utc)   # Saturday 07:00 UTC
MILLION_EACH = {"prompt_cache_hit_tokens": 1_000_000,
                "prompt_cache_miss_tokens": 1_000_000,
                "completion_tokens": 1_000_000}


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    for k in list(ai.os.environ):
        if "_KEY_" in k:
            monkeypatch.delenv(k)
    monkeypatch.setenv("AI_KEY_STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(ai.time, "sleep", lambda s: None)


def rows():
    with open(costs.LEDGER, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.mark.parametrize("t, usd", [(MON_PEAK, 1.506), (MON_OFFPEAK, 0.753), (SAT_MORNING, 0.753)])
def test_deepseek_price_peak_and_off_peak(t, usd):
    assert costs.call_cost("deepseek:deepseek-v4-flash", MILLION_EACH, t) == pytest.approx(usd)


def test_unpriced_models_are_free():
    assert costs.call_cost("gemini-3.5-flash", MILLION_EACH, MON_PEAK) == 0
    assert costs.call_cost("openrouter:stealth/space-bunny-alpha", MILLION_EACH, MON_PEAK) == 0


GEMINI_2027 = datetime(2027, 1, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize("model, t, usage, usd", [
    ("gemini-3.8-flash", MON_OFFPEAK, MILLION_EACH, 4.575),
    ("gemini-3.8-flash", MON_PEAK, MILLION_EACH, 4.575),
    ("gemini-3.7-flash", GEMINI_2027, MILLION_EACH, 9.15),
    ("gemini-3.1-pro-preview", MON_PEAK,
     {"prompt_cache_hit_tokens": 100_000, "prompt_cache_miss_tokens": 50_000, "completion_tokens": 10_000}, 0.24),
    ("gemini-3.1-pro-preview", MON_PEAK,
     {"prompt_cache_hit_tokens": 300_000, "prompt_cache_miss_tokens": 100_000, "completion_tokens": 10_000}, 0.70),
])
def test_gemini_price(model, t, usage, usd):
    assert costs.call_cost(model, usage, t) == pytest.approx(usd)


def test_unpriced_gemini_model_warns_and_logs_zero(capsys):
    assert costs.record("gemini-3.5-flash", "x", MILLION_EACH, MON_PEAK) == 0
    assert "no price known for gemini-3.5-flash" in capsys.readouterr().out


def test_record_appends_and_carries_all_time_total(capsys):
    costs.LEDGER.write_text(
        "time_utc,model,label,cache_hit_tokens,cache_miss_tokens,output_tokens,usd\n"
        "2026-09-28 10:00:00,deepseek:deepseek-v4-flash,M-i p1,0,0,0,2.000000\n",
        encoding="utf-8",
    )
    costs.record("deepseek:deepseek-v4-flash", "M-i p2", MILLION_EACH, MON_OFFPEAK)
    costs.record("deepseek:deepseek-v4-flash", "M-i p3", MILLION_EACH, MON_OFFPEAK)

    assert [r["label"] for r in rows()] == ["M-i p1", "M-i p2", "M-i p3"]
    assert rows()[-1]["usd"] == "0.753000"
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last == ("[cost] deepseek:deepseek-v4-flash $0.7530 this call, "
                    "$1.5060 this run, $3.5060 all time")


def test_deepseek_call_is_logged_with_its_label(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_KEY_1", "d1")
    usage = {"prompt_cache_hit_tokens": 100, "prompt_cache_miss_tokens": 900, "completion_tokens": 50}
    monkeypatch.setattr(ai.ai_openai_compat, "chat", lambda *a: ("ok", 200, "", usage))

    assert ai.call_gemini(ai.make_rotator([]), "p", "s",
                          models=["deepseek:deepseek-v4-flash"], label="M-i p280-300") == "ok"
    (row,) = rows()
    assert (row["model"], row["label"]) == ("deepseek:deepseek-v4-flash", "M-i p280-300")
    assert (row["cache_hit_tokens"], row["cache_miss_tokens"], row["output_tokens"]) == ("100", "900", "50")
    assert float(row["usd"]) > 0


def test_billed_call_without_text_is_still_logged(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_KEY_1", "d1")
    usage = {"prompt_cache_miss_tokens": 900, "completion_tokens": 50}
    replies = [(None, 200, "no text", usage), ("ok", 200, "", usage)]
    monkeypatch.setattr(ai.ai_openai_compat, "chat", lambda *a: replies.pop(0))

    ai.call_gemini(ai.make_rotator([]), "p", "s", models=["deepseek:deepseek-v4-flash"])
    assert len(rows()) == 2


def test_gemini_call_is_logged_with_thinking_counted_as_output(monkeypatch):
    monkeypatch.setenv("GEMINI_KEY_1", "g1")
    md = types.SimpleNamespace(prompt_token_count=1000, cached_content_token_count=200,
                               candidates_token_count=300, thoughts_token_count=100)

    class FakeClient:
        def __init__(self, api_key):
            self.models = self

        def generate_content(self, **kw):
            return types.SimpleNamespace(text="ok", usage_metadata=md)

    import google.genai
    monkeypatch.setattr(google.genai, "Client", FakeClient)

    assert ai.call_gemini(ai.make_rotator([]), "p", "s", models=["gemini-3.7-flash"]) == "ok"
    (row,) = rows()
    assert (row["cache_hit_tokens"], row["cache_miss_tokens"], row["output_tokens"]) == ("200", "800", "400")
    assert float(row["usd"]) > 0


def test_chat_returns_the_usage_report(monkeypatch):
    import requests

    usage = {"prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 7, "completion_tokens": 12}
    body = {"choices": [{"message": {"content": "Hi!"}}], "usage": usage}
    resp = types.SimpleNamespace(status_code=200, text="", json=lambda: body)
    monkeypatch.setattr(requests, "post", lambda *a, **k: resp)

    assert ai.ai_openai_compat.chat("deepseek", "k", "m", "s", "p", 10, 5) == ("Hi!", 200, "", usage)


def test_openrouter_uses_its_reported_cost_and_tokens(capsys):
    usage = {"prompt_tokens": 1234, "completion_tokens": 56, "cost": 0.0021,
             "prompt_tokens_details": {"cached_tokens": 200}}
    costs.record("openrouter:some/paid-model", "x", usage, MON_OFFPEAK)
    costs.record("openrouter:stealth/space-bunny-alpha", "y", {**usage, "cost": 0}, MON_PEAK)
    first, second = rows()
    assert (first["cache_hit_tokens"], first["cache_miss_tokens"], first["usd"]) == ("200", "1034", "0.002100")
    assert second["usd"] == "0.000000"
    assert "$0.0021 this run" in capsys.readouterr().out.strip().splitlines()[-1]


def test_damaged_ledger_does_not_raise(capsys):
    costs.LEDGER.write_text("time_utc,model,label,cache_hit_tokens,cache_miss_tokens,output_tokens,usd\n"
                            "x,y,z,1,2,3,not-a-number\n", encoding="utf-8")
    assert costs.record("deepseek:deepseek-v4-flash", "x", MILLION_EACH, MON_PEAK) == pytest.approx(1.506)
    assert "could not read" in capsys.readouterr().out


def test_tool_calls_carry_the_label(monkeypatch):
    seen = []
    monkeypatch.setattr(ai, "call_gemini_with_tools", lambda *a, **k: seen.append(k["label"]) or "ok")
    ai.call_ai_with_logging(rotator=None, prompt="p", book_id="Sv-i", chunk_id="p1-5",
                            log_dir=str(costs.LEDGER.parent), tools=["t"], tool_executor=lambda *a: {})
    assert seen == ["Sv-i p1-5"]


def test_bad_or_missing_openrouter_cost_warns_and_logs_zero(capsys):
    assert costs.record("openrouter:x/y", "a", {"prompt_tokens": 5, "cost": "n/a"}, MON_PEAK) == 0
    assert costs.record("openrouter:x/y", "b", {"prompt_tokens": 5}, MON_PEAK) == 0
    out = capsys.readouterr().out
    assert "could not price" in out and "OpenRouter sent no cost" in out
    assert [r["usd"] for r in rows()] == ["0.000000", "0.000000"]
