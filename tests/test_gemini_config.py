import types

import pytest
from google import genai
from google.genai import _extra_utils

from common import ai_client as ai


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    for k in list(ai.os.environ):
        if "_KEY_" in k:
            monkeypatch.delenv(k)
    monkeypatch.setenv("AI_KEY_STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(ai.time, "sleep", lambda s: None)


def fake_client(responses, configs):
    class FakeModels:
        def generate_content(self, model, contents, config):
            configs.append(config)
            return responses.pop(0)

    class FakeClient:
        def __init__(self, api_key):
            self.models = FakeModels()

    return FakeClient


def reply(text=None, calls=None):
    return types.SimpleNamespace(
        text=text, function_calls=calls, candidates=None, usage_metadata=None,
    )


def test_plain_call_switches_library_function_calling_off(monkeypatch):
    configs = []
    monkeypatch.setattr(genai, "Client", fake_client([reply("ok")], configs))
    rotator = ai.KeyRotator(["k1"])

    assert ai.call_gemini(rotator, "p", "s", model="gemini-x") == "ok"
    assert [_extra_utils.should_disable_afc(c) for c in configs] == [True]


def test_tool_loop_switches_it_off_in_every_round_including_the_forced_one(monkeypatch):
    configs = []
    call = types.SimpleNamespace(name="get_text_range", args={})
    monkeypatch.setattr(
        genai, "Client",
        fake_client([reply(calls=[call]), reply(calls=[call]), reply("final")], configs),
    )
    rotator = ai.KeyRotator(["k1"])

    text = ai.call_gemini_with_tools(
        rotator, "p", "s", model="gemini-x", tools=[],
        tool_executor=lambda name, args: {"ok": True}, max_rounds=0,
    )

    assert text == "final"
    assert [_extra_utils.should_disable_afc(c) for c in configs] == [True, True, True]
