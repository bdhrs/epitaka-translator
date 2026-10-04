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
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# A subscription usage limit can come back as plain result text with no API
# status ("Claude AI usage limit reached|<epoch>", "You've hit your limit · resets 3pm").
# Report it as 429 so the retry loop parks the model and runner.sh sleeps.
_LIMIT_RE = re.compile(r"usage limit|hit your (usage |session |weekly )?limit|rate.?limit", re.I)

# "resets 9:30am (Asia/Colombo)", "resets 3pm", "resets Oct 10, 10:30pm (Asia/Colombo)"
_RESET_RE = re.compile(
    r"resets\s+(?:(?P<mon>[A-Z][a-z]{2})\w*\s+(?P<day>\d{1,2}),?\s+)?"
    r"(?P<hour>\d{1,2})(?::(?P<min>\d{2}))?\s*(?P<ampm>[ap]m)\b(?:\s*\((?P<tz>[^)]+)\))?", re.I)
_EPOCH_RE = re.compile(r"limit reached\|(\d{9,})")

# When the last limit message said the usage window opens again; ai_client prints
# it for runner.sh, which then sleeps until then instead of guessing.
last_reset: datetime | None = None


def parse_reset(text: str, now: datetime | None = None) -> datetime | None:
    """The reset time a limit message names, in UTC, or None when it names none."""
    now = now or datetime.now(timezone.utc)
    m = _EPOCH_RE.search(text)
    if m:
        return datetime.fromtimestamp(int(m.group(1)), timezone.utc)
    m = _RESET_RE.search(text)
    if not m:
        return None
    try:
        tz = ZoneInfo(m.group("tz")) if m.group("tz") else now.astimezone().tzinfo
        local_now = now.astimezone(tz)
        hour = int(m.group("hour")) % 12 + (12 if m.group("ampm").lower() == "pm" else 0)
        at = local_now.replace(hour=hour, minute=int(m.group("min") or 0), second=0, microsecond=0)
        if m.group("mon"):
            at = at.replace(month=datetime.strptime(m.group("mon"), "%b").month, day=int(m.group("day")))
            if at < local_now - timedelta(days=1):
                at = at.replace(year=at.year + 1)
        elif at < local_now - timedelta(hours=1):
            # A time that passed over an hour ago means tomorrow. One that passed
            # minutes ago stays in the past: the displayed time is rounded, so the
            # limit may outlast it by a little, and the caller retries soon.
            at += timedelta(days=1)
    except (ZoneInfoNotFoundError, ValueError):
        return None
    return at.astimezone(timezone.utc)


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
        # What this call is worth at API prices; the subscription charges nothing per call.
        "api_usd":                  body.get("total_cost_usd"),
    }
    if body.get("is_error") or not body.get("result"):
        global last_reset
        last_reset = parse_reset(str(body.get("result"))) or last_reset
        status = body.get("api_error_status")
        if status is None and _LIMIT_RE.search(str(body.get("result"))):
            status = 429
        return None, status, (
            f"{body.get('subtype')}: {str(body.get('result'))[:300]}"
        ), usage
    return body["result"], 200, "", usage
