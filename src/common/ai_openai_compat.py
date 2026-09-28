"""
ai_openai_compat.py — one call to an OpenAI-compatible chat/completions
endpoint (DeepSeek, OpenRouter). Cut down from dpd-db's
tools/ai_openai_compat.py. Retries, key rotation and model fallback live in
ai_client._generate_with_retry, not here.
"""

import requests

CHAT_URLS = {
    "deepseek":   "https://api.deepseek.com/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
}

# DeepSeek's reasoning mode can spend the whole output budget on hidden
# reasoning and return empty content (seen in dpd-db and ai_client_bai.py).
EXTRA_PAYLOAD = {
    "deepseek": {"thinking": {"type": "disabled"}},
}


def chat(
    provider:      str,
    key:           str,
    model:         str,
    system_prompt: str,
    prompt:        str,
    max_tokens:    int,
    timeout:       float,
) -> tuple[str | None, int | None, str]:
    """
    Send one prompt. Returns (text, http_status, error). `text` is None on
    any failure; `http_status` is None when no HTTP response came back.
    """
    payload = {
        "model":      model,
        "stream":     False,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": prompt},
        ],
        **EXTRA_PAYLOAD.get(provider, {}),
    }
    try:
        r = requests.post(
            CHAT_URLS[provider],
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as e:
        return None, None, f"{type(e).__name__}: {e}"

    if r.status_code != 200:
        return None, r.status_code, f"HTTP {r.status_code}: {r.text[:300]}"

    try:
        body = r.json()
    except ValueError:
        return None, r.status_code, f"non-JSON body: {r.text[:300]}"

    # OpenRouter can answer HTTP 200 with an error object and no choices.
    choices = body.get("choices") or []
    text = ((choices[0].get("message") or {}).get("content") if choices else None)
    if not text:
        err = body.get("error") or {}
        finish = choices[0].get("finish_reason") if choices else None
        return None, err.get("code") or r.status_code, (
            f"no text (finish_reason={finish}, error={err.get('message')})"
        )
    return text, r.status_code, ""
