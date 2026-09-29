import pytest

from common import ai_client as ai


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    for k in list(ai.os.environ):
        if "_KEY_" in k:
            monkeypatch.delenv(k)
    monkeypatch.setenv("AI_KEY_STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(ai.time, "sleep", lambda s: None)


def fake_chat(replies, calls):
    """replies: list of (text, status, error), consumed per call."""
    def _chat(provider, key, model, system_prompt, prompt, max_tokens, timeout):
        calls.append((provider, key, model, system_prompt, prompt))
        text, status, err = replies.pop(0)
        return text, status, err, {}
    return _chat


def test_deepseek_success_passes_prompt_and_strips_prefix(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_KEY_1", "d1")
    calls = []
    monkeypatch.setattr(ai.ai_openai_compat, "chat", fake_chat([("hello", 200, "")], calls))

    used = []
    text = ai.call_gemini(
        ai.make_rotator([]), "the prompt", "the system",
        models=["deepseek:deepseek-v4-flash"], used_model=used,
    )
    assert text == "hello"
    assert calls == [("deepseek", "d1", "deepseek-v4-flash", "the system", "the prompt")]
    assert used == ["deepseek:deepseek-v4-flash"]


def test_three_429s_move_the_pool_to_the_next_model(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_KEY_1", "d1")
    monkeypatch.setenv("OPENROUTER_KEY_1", "o1")
    calls = []
    replies = [(None, 429, "slow")] * 3 + [("from openrouter", 200, "")]
    monkeypatch.setattr(ai.ai_openai_compat, "chat", fake_chat(replies, calls))

    text = ai.call_gemini(
        ai.make_rotator([]), "p", "s",
        models=["deepseek:deepseek-v4-flash", "openrouter:stealth/space-bunny-alpha"],
    )
    assert text == "from openrouter"
    assert [c[0] for c in calls] == ["deepseek"] * 3 + ["openrouter"]


def test_401_removes_only_that_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_KEY_1", "d1")
    monkeypatch.setenv("DEEPSEEK_KEY_2", "d2")
    monkeypatch.setenv("GEMINI_KEY_1", "g1")
    calls = []
    monkeypatch.setattr(ai.ai_openai_compat, "chat",
                        fake_chat([(None, 401, "bad key"), ("ok", 200, "")], calls))

    rot = ai.make_rotator([])
    text = ai.call_gemini(rot, "p", "s", models=["deepseek:deepseek-v4-flash"])
    assert text == "ok"
    assert [c[1] for c in calls] == ["d1", "d2"]
    assert rot.remaining_key_count() == 2


@pytest.mark.parametrize("status", [401, 402, 403])
def test_auth_and_balance_errors_remove_the_key(monkeypatch, status):
    monkeypatch.setenv("DEEPSEEK_KEY_1", "d1")
    monkeypatch.setenv("DEEPSEEK_KEY_2", "d2")
    calls = []
    monkeypatch.setattr(ai.ai_openai_compat, "chat",
                        fake_chat([(None, status, "no"), ("ok", 200, "")], calls))

    rot = ai.make_rotator([])
    assert ai.call_gemini(rot, "p", "s", models=["deepseek:deepseek-v4-flash"]) == "ok"
    assert rot.remaining_key_count() == 1


def test_missing_provider_key_is_logged_by_name(monkeypatch, caplog):
    monkeypatch.setenv("DEEPSEEK_KEY_1", "d1")
    monkeypatch.setattr(ai.ai_openai_compat, "chat", fake_chat([("ok", 200, "")], []))

    text = ai.call_gemini(ai.make_rotator([]), "p", "s",
                          models=["openrouter:stealth/space-bunny-alpha", "deepseek:deepseek-v4-flash"])
    assert text == "ok"
    assert "OPENROUTER_KEY_1" in caplog.text


@pytest.mark.parametrize("env, model", [
    ({"DEEPSEEK_KEY_1": "d1"}, "deepseek:deepseek-v4-flash"),
    ({"OPENROUTER_KEY_1": "o1"}, "openrouter:stealth/space-bunny-alpha"),
    ({"DEEPSEEK_KEY_1": "d1", "OPENROUTER_KEY_1": "o1"}, "deepseek:deepseek-v4-flash"),
])
def test_default_chain_survives_missing_providers(monkeypatch, env, model):
    import sys
    sys.argv = sys.argv[:1]
    import book_translator as bt

    for k, v in env.items():
        monkeypatch.setenv(k, v)
    calls = []
    monkeypatch.setattr(ai.ai_openai_compat, "chat", fake_chat([("ok", 200, "")], calls))

    def no_gemini(*a, **k):
        raise AssertionError("run must not end as all-keys-exhausted")
    monkeypatch.setattr(ai, "_fatal_all_keys_exhausted", no_gemini)

    used = []
    text = ai.call_gemini(ai.make_rotator([]), "p", "s",
                          models=list(bt.FALLBACK_MODEL_CHAIN), used_model=used)
    assert text == "ok"
    assert used == [model]
    assert [c[0] for c in calls] == [model.split(":")[0]]
