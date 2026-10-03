"""
ai_claude_code.py — one call through the local Claude Code CLI, so the
translator can run on a Claude Code subscription instead of an API key.
Same return shape as ai_openai_compat.chat. Retries, key rotation and model
fallback live in ai_client._generate_with_retry, not here.
"""

import json
import os
import re
import subprocess
import tempfile

# A subscription usage limit can come back as plain result text with no API
# status ("Claude AI usage limit reached|<epoch>", "You've hit your limit · resets 3pm").
# Report it as 429 so the retry loop parks the model and runner.sh sleeps.
_LIMIT_RE = re.compile(r"usage limit|hit your (usage )?limit|rate.?limit", re.I)


def chat(
    model:         str,
    system_prompt: str,
    prompt:        str,
    timeout:       float,
) -> tuple[str | None, int | None, str, dict]:
    """
    Send one prompt. Returns (text, http_status, error, usage). `text` is None
    on any failure; `http_status` is the API status Claude Code reports, or
    None. `usage` is in the shape costs.record reads.
    """
    cmd = ["claude", "-p", "--model", model, "--output-format", "json",
           "--tools", "", "--setting-sources", "", "--disable-slash-commands",
           "--strict-mcp-config", "--no-session-persistence"]
    if system_prompt:
        cmd += ["--system-prompt", system_prompt]
    # An API key in the environment would make Claude Code bill the API, not the subscription.
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    # A neutral folder, so no CLAUDE.md or AGENTS.md of this repo is read into the prompt.
    with tempfile.TemporaryDirectory() as cwd:
        try:
            run = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                                 timeout=timeout, cwd=cwd, env=env)
        except (OSError, subprocess.TimeoutExpired) as e:
            return None, None, f"{type(e).__name__}: {e}", {}

    try:
        body = json.loads(run.stdout)
    except ValueError:
        return None, None, f"exit {run.returncode}, non-JSON output: {(run.stdout or run.stderr)[:300]}", {}

    u = body.get("usage") or {}
    # Cache reads are billed as input; cache writes are the cache-miss part.
    usage = {
        "prompt_cache_hit_tokens":  u.get("cache_read_input_tokens", 0),
        "prompt_cache_miss_tokens": u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0),
        "completion_tokens":        u.get("output_tokens", 0),
    }
    if body.get("is_error") or not body.get("result"):
        status = body.get("api_error_status")
        if status is None and _LIMIT_RE.search(str(body.get("result"))):
            status = 429
        return None, status, (
            f"{body.get('subtype')}: {str(body.get('result'))[:300]}"
        ), usage
    return body["result"], 200, "", usage
