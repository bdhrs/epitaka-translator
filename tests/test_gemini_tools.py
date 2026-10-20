import types
from typing import cast

import pytest

from common import ai_client as ai

MODEL = "gemini-3.7-flash"


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    for k in list(ai.os.environ):
        if "_KEY_" in k:
            monkeypatch.delenv(k)
    monkeypatch.setenv("AI_KEY_STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(ai.time, "sleep", lambda _: None)


def reply_with(monkeypatch, response):
    monkeypatch.setattr(ai, "_generate_with_retry", lambda *_: (response, "k", MODEL))


def call_with_tools(**kwargs):
    return ai.call_gemini_with_tools(cast(ai.KeyRotator, None), "p", "s", models=[MODEL], **kwargs)


def test_no_models_returns_none_instead_of_crashing():
    assert ai.call_gemini_with_tools(cast(ai.KeyRotator, None), "p", "s", models=[]) is None


@pytest.mark.parametrize("candidates, reason", [
    ([types.SimpleNamespace(finish_reason="MAX_TOKENS")], "MAX_TOKENS"),
    ([], "None"),
    (None, "None"),
])
def test_a_reply_with_no_text_and_no_tool_call_returns_none_and_logs_why(monkeypatch, candidates, reason):
    reply_with(monkeypatch, types.SimpleNamespace(function_calls=None, text="", candidates=candidates))
    lines = []

    assert call_with_tools(log=lines.append) is None
    assert f"finish_reason={reason}" in lines[-1]


def test_a_tool_call_without_an_executor_says_so(monkeypatch):
    call = types.SimpleNamespace(name="get_text_range", args={})
    reply_with(monkeypatch, types.SimpleNamespace(function_calls=[call], text="",
                                                  candidates=[types.SimpleNamespace(content=None)]))

    with pytest.raises(TypeError, match="no tool_executor was given"):
        call_with_tools()
