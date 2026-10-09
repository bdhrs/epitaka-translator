import requests

from common import ai_openai_compat as compat


class FakeResponse:
    def __init__(self, status_code, body=None, text=""):
        self.status_code = status_code
        self._body = body
        self.text = text

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


def fake_post(response, seen):
    def _post(url, headers, json, timeout):
        seen.update(url=url, headers=headers, json=json, timeout=timeout)
        if isinstance(response, Exception):
            raise response
        return response
    return _post


def call(provider="deepseek"):
    return compat.chat(provider, "k1", "m1", "sys", "user", 65536, 30)


def test_success_sends_expected_payload(monkeypatch):
    seen = {}
    body = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
    monkeypatch.setattr(requests, "post", fake_post(FakeResponse(200, body), seen))

    assert call() == ("ok", 200, "", {})
    assert seen["url"] == "https://api.deepseek.com/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer k1"
    assert seen["json"]["thinking"] == {"type": "disabled"}
    assert seen["json"]["max_tokens"] == 65536
    assert seen["json"]["messages"][0] == {"role": "system", "content": "sys"}


def test_openrouter_has_no_thinking(monkeypatch):
    seen = {}
    body = {"choices": [{"message": {"content": "ok"}}]}
    monkeypatch.setattr(requests, "post", fake_post(FakeResponse(200, body), seen))

    call("openrouter")
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert "thinking" not in seen["json"]
    assert seen["json"]["max_tokens"] == 65536


def test_azure_url_comes_from_env(monkeypatch):
    seen = {}
    body = {"choices": [{"message": {"content": "ok"}}]}
    monkeypatch.setattr(requests, "post", fake_post(FakeResponse(200, body), seen))
    monkeypatch.setenv("AZURE_BASE_URL", "https://example.services.ai.azure.com/openai/v1/")

    assert call("azure")[0] == "ok"
    assert seen["url"] == "https://example.services.ai.azure.com/openai/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer k1"


def test_azure_without_base_url_fails_without_a_request(monkeypatch):
    seen = {}
    monkeypatch.setattr(requests, "post", fake_post(FakeResponse(200, {}), seen))
    monkeypatch.delenv("AZURE_BASE_URL", raising=False)

    text, status, error, _ = call("azure")
    assert (text, status, seen) == (None, None, {})
    assert "AZURE_BASE_URL" in error


def test_http_429_returns_status(monkeypatch):
    monkeypatch.setattr(requests, "post", fake_post(FakeResponse(429, text="slow down"), {}))
    text, status, error, _ = call()
    assert (text, status) == (None, 429)
    assert "slow down" in error


def test_http_200_error_body_without_choices(monkeypatch):
    body = {"error": {"code": 429, "message": "free tier limit"}}
    monkeypatch.setattr(requests, "post", fake_post(FakeResponse(200, body), {}))
    text, status, error, _ = call("openrouter")
    assert (text, status) == (None, 429)
    assert "free tier limit" in error


def test_network_error_has_no_status(monkeypatch):
    monkeypatch.setattr(requests, "post", fake_post(requests.ConnectionError("down"), {}))
    text, status, error, _ = call()
    assert (text, status) == (None, None)
    assert "ConnectionError" in error
