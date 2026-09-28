import time

import pytest

from common import ai_client as ai


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    for k in list(ai.os.environ):
        if "_KEY_" in k:
            monkeypatch.delenv(k)
    monkeypatch.setenv("AI_KEY_STATE_FILE", str(tmp_path / "state.json"))


def test_split_model():
    assert ai.split_model("deepseek:deepseek-v4-flash") == ("deepseek", "deepseek-v4-flash")
    assert ai.split_model("openrouter:x/y:free") == ("openrouter", "x/y:free")
    assert ai.split_model("gemini-3.7-flash") == ("gemini", "gemini-3.7-flash")


def test_deepseek_model_never_gets_a_gemini_key(monkeypatch):
    monkeypatch.setenv("GEMINI_KEY_1", "g1")
    monkeypatch.setenv("GEMINI_KEY_2", "g2")
    monkeypatch.setenv("DEEPSEEK_KEY_1", "d1")
    rot = ai.make_rotator([])

    got = {rot.acquire(10, model="deepseek:deepseek-v4-flash") for _ in range(3)}
    assert got == {"d1"}
    assert rot.acquire(10, model="gemini-3.7-flash") in {"g1", "g2"}


def test_missing_provider_raises_at_once_naming_the_key(monkeypatch):
    monkeypatch.setenv("GEMINI_KEY_1", "g1")
    rot = ai.make_rotator([])

    start = time.monotonic()
    with pytest.raises(ai.AllKeysExhaustedError, match="DEEPSEEK_KEY_1"):
        rot.acquire(10, model="deepseek:deepseek-v4-flash")
    assert time.monotonic() - start < 1


def test_deepseek_only_env_builds_a_rotator(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_KEY_1", "d1")
    rot = ai.make_rotator([])
    assert rot.acquire(10, model="deepseek:deepseek-v4-flash") == "d1"


def test_explicit_api_keys_are_gemini():
    rot = ai.make_rotator(["x1"])
    assert rot.acquire(10, model="gemini-3.7-flash") == "x1"
    with pytest.raises(ai.AllKeysExhaustedError):
        rot.acquire(10, model="openrouter:stealth/space-bunny-alpha")


def test_gemini_round_robin_is_even_with_deepseek_keys(monkeypatch):
    for i in (1, 2, 3):
        monkeypatch.setenv(f"GEMINI_KEY_{i}", f"g{i}")
    monkeypatch.setenv("DEEPSEEK_KEY_1", "d1")
    monkeypatch.setenv("DEEPSEEK_KEY_2", "d2")
    rot = ai.make_rotator([])
    rot._rpm_limit = 100

    got = [rot.acquire(10, model="gemini-3.7-flash") for _ in range(6)]
    assert got == ["g1", "g2", "g3", "g1", "g2", "g3"]


def test_state_file_never_holds_the_key(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPSEEK_KEY_1", "sk-secret-123")
    rot = ai.make_rotator([])
    key = rot.acquire(10, model="deepseek:deepseek-v4-flash")
    rot.record_result(key, success=True, model="deepseek:deepseek-v4-flash")
    rot.remove(key, reason="test", model="deepseek:deepseek-v4-flash")

    text = "".join(p.read_text() for p in tmp_path.glob("state*.json"))
    assert "DEEPSEEK_KEY_1" in text
    assert "sk-secret-123" not in text
