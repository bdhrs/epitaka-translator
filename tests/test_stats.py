import csv
import sqlite3
import types
from datetime import datetime, timezone

import pytest

import stats
from common import ai_client as ai
from common import costs

OLD_HEADER = "time_utc,model,label,cache_hit_tokens,cache_miss_tokens,output_tokens,usd\n"
LIMIT_TEXT = "success: You've hit your session limit · resets 9:30am (Asia/Colombo)"


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


def source_db(tmp_path):
    """A tiny epitaka.db: D-i paragraphs 521-525 with 4 lines each, one of them a bare number."""
    path = tmp_path / "epitaka.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE sentences (book_id TEXT, para_id INT, line_id INT, pali TEXT)")
    conn.execute("CREATE TABLE books (book_id TEXT, category TEXT, nikaya TEXT)")
    conn.execute("INSERT INTO books VALUES ('D-i', 'Mūla', 'Sutta Piṭaka')")
    for para in range(521, 526):
        for line, pali in enumerate(["Evaṃ me sutaṃ", "ekaṃ samayaṃ", "bhagavā", "12"], start=1):
            conn.execute("INSERT INTO sentences VALUES ('D-i', ?, ?, ?)", (para, line, pali))
    conn.commit()
    conn.close()
    return path


def test_old_ledger_keeps_its_rows_and_gains_the_new_columns():
    costs.LEDGER.write_text(OLD_HEADER + "2026-09-28 10:00:00,deepseek:deepseek-v4-flash,M-i p1,5,6,7,2.000000\n",
                            encoding="utf-8")
    costs.record("deepseek:deepseek-v4-flash", "M-i p2", {"completion_tokens": 3}, lines=40, seconds=36.4)
    old, new = rows()
    assert (old["label"], old["usd"], old["lines"], old["status"]) == ("M-i p1", "2.000000", "", "")
    assert (new["lines"], new["status"], new["seconds"]) == ("40", "ok", "36.4")
    assert list(new) == costs._FIELDS


def test_claude_api_value_is_logged_beside_a_zero_charge():
    costs.record("claude:sonnet", "D-i p1-20_L1-11", {"completion_tokens": 9, "api_usd": 0.0074}, lines=54)
    (row,) = rows()
    assert (row["usd"], row["api_usd"]) == ("0.000000", "0.007400")


def test_claude_limit_gets_a_row_that_keeps_the_reset_time(monkeypatch):
    monkeypatch.setenv("CLAUDE_KEY_1", "c1")
    zero = {"prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 0, "completion_tokens": 0, "api_usd": 0}
    replies = [(None, 429, LIMIT_TEXT, zero), ("ok", 200, "", {**zero, "completion_tokens": 50})]
    monkeypatch.setattr(ai.ai_claude_code, "chat", lambda *a: replies.pop(0))

    assert ai.call_gemini(ai.make_rotator([]), "p", "s", models=["claude:sonnet"],
                          label="D-i p1-5", lines=12) == "ok"
    limit, ok = rows()
    assert (limit["status"], limit["lines"], limit["output_tokens"]) == ("limit", "12", "0")
    assert "resets 9:30am (Asia/Colombo)" in limit["detail"]
    assert (ok["status"], ok["lines"]) == ("ok", "12")


def test_gemini_failure_is_logged_too(monkeypatch):
    monkeypatch.setenv("GEMINI_KEY_1", "g1")
    md = types.SimpleNamespace(prompt_token_count=10, cached_content_token_count=0,
                               candidates_token_count=5, thoughts_token_count=0)
    attempts = []

    class FakeClient:
        def __init__(self, api_key):
            self.models = self

        def generate_content(self, **kw):
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("429 RESOURCE_EXHAUSTED: daily quota")
            return types.SimpleNamespace(text="ok", usage_metadata=md)

    import google.genai
    monkeypatch.setattr(google.genai, "Client", FakeClient)

    assert ai.call_gemini(ai.make_rotator([]), "p", "s", models=["gemini-3.7-flash"], lines=7) == "ok"
    failed, ok = rows()
    assert (failed["status"], failed["lines"], failed["output_tokens"]) == ("limit", "7", "0")
    assert "RESOURCE_EXHAUSTED" in failed["detail"]
    assert ok["status"] == "ok"


# Times and labels below are copied from the real server log of 2026-10-03/04 (UTC);
# the token counts are placeholders (an ok call has output, a limit hit has none).
SERVER_LOG = [
    ("2026-10-03 16:16:15", "D-i p1-20_L1-11", 5000),
    ("2026-10-03 16:28:30", "D-i p21-60_L1-2", 5000),
    ("2026-10-03 16:28:52", "D-i p61-67_L1-2", 5000),
    ("2026-10-03 17:01:07", "D-i p521-525_L1-20", 0),
    ("2026-10-03 17:01:29", "D-i p521-525_L1-20", 0),
    ("2026-10-03 17:01:51", "D-i p521-525_L1-20", 0),
    ("2026-10-03 23:03:21", "D-i p521-525_L1-20", 5000),
]


def old_ledger(tmp_path):
    path = tmp_path / "old.csv"
    path.write_text(OLD_HEADER + "".join(
        f"{t},claude:sonnet,{label},0,100,{out},0.000000\n" for t, label, out in SERVER_LOG), encoding="utf-8")
    return path


def test_old_rows_get_status_from_tokens_and_lines_from_the_source(tmp_path):
    db = source_db(tmp_path)
    calls, estimated, skipped = stats.load_calls(old_ledger(tmp_path), db)
    assert [c.status for c in calls] == ["ok"] * 3 + ["limit"] * 3 + ["ok"]
    # p521-525 is 5 paragraphs x 3 translatable lines (the bare number is skipped)
    assert calls[-1].lines == 15
    # a single-paragraph label with a line range counts only that range
    assert stats.estimate_lines(sqlite3.connect(db), "D-i p521-521_L1-2") == 2
    assert skipped == 0 and estimated == 1  # the test database holds only paragraphs 521-525
    assert all(c.api_usd is None for c in calls)  # old Claude rows have no API value


def test_work_time_counts_gaps_between_ok_calls_only(tmp_path):
    calls, _, _ = stats.load_calls(old_ledger(tmp_path), source_db(tmp_path))
    work = [c.work for c in calls]
    # 16:16:15 starts the run (0); 16:28:30 is 735 s later, over the idle limit (0);
    # 16:28:52 is 22 s after that; the limit rows and the 23:03 restart add nothing.
    assert work == [0, 0, 22, 0, 0, 0, 0]


def test_sessions_end_by_limit_and_split_after_a_long_wait(tmp_path):
    calls, _, _ = stats.load_calls(old_ledger(tmp_path), source_db(tmp_path))
    first, second = stats.sessions(calls)  # the 735 s gap after the first call stays inside one session
    assert (first.calls, first.ended) == (3, "limit")
    assert (second.calls, second.ended) == (1, "-")


def test_a_retry_that_works_clears_the_earlier_failure(tmp_path):
    ledger = tmp_path / "retry.csv"
    ledger.write_text(
        "time_utc,model,label,cache_hit_tokens,cache_miss_tokens,output_tokens,usd,lines,status,seconds,api_usd,detail\n"
        "2026-10-03 10:00:00,claude:sonnet,D-i p1-5,0,10,5,0,50,ok,60.0,0.2,\n"
        "2026-10-03 10:01:00,claude:sonnet,D-i p6-9,0,0,0,0,50,limit,5.0,0,hit limit\n"
        "2026-10-03 10:01:30,claude:sonnet,D-i p6-9,0,10,5,0,50,ok,60.0,0.2,\n", encoding="utf-8")
    calls, _, _ = stats.load_calls(ledger, tmp_path / "missing.db")
    (only,) = stats.sessions(calls)
    assert (only.calls, only.lines, only.ended) == (2, 100, "-")


def test_buckets_use_local_time():
    t = datetime(2026, 10, 3, 20, 0, tzinfo=timezone.utc)
    colombo = timezone(__import__("datetime").timedelta(hours=5, minutes=30))
    assert stats.bucket_of(t, "day", timezone.utc) == "2026-10-03"
    assert stats.bucket_of(t, "day", colombo) == "2026-10-04"
    assert stats.bucket_of(t, "week", colombo) == "week of 2026-09-28"
    assert stats.bucket_of(t, "month", colombo) == "2026-10"


def test_report_shows_lines_and_the_payment_kind_of_each_model(tmp_path):
    ledger = tmp_path / "mixed.csv"
    ledger.write_text(
        "time_utc,model,label,cache_hit_tokens,cache_miss_tokens,output_tokens,usd,lines,status,seconds,api_usd,detail\n"
        "2026-10-03 10:00:00,deepseek:deepseek-v4-flash,D-i p1-5,0,10,5,0.010000,50,ok,36.0,0.010000,\n"
        "2026-10-03 10:01:00,claude:sonnet,D-i p6-9,0,10,5,0.000000,54,ok,60.0,0.200000,\n"
        "2026-10-03 10:02:00,gemini-3.7-flash,D-i p10-12,0,10,5,0.003000,30,ok,20.0,0.003000,\n", encoding="utf-8")
    calls, _, _ = stats.load_calls(ledger, tmp_path / "missing.db")
    out = stats.period_report(calls, "day", timezone.utc, 14)
    by_model = {line.split()[1]: line for line in out.splitlines() if "2026-10-03" in line}
    assert "5,000" in by_model["deepseek:deepseek-v4-flash"]  # 50 lines in 36 s
    assert by_model["deepseek:deepseek-v4-flash"].rstrip().endswith("$0.01")
    assert by_model["claude:sonnet"].rstrip().endswith("plan")
    assert by_model["gemini-3.7-flash"].rstrip().endswith("free")
    assert "$0.20" in by_model["claude:sonnet"]


def test_weekly_capacity_comes_from_lines_this_week_over_percent_used(tmp_path):
    ledger = tmp_path / "week.csv"
    ledger.write_text(
        "time_utc,model,label,cache_hit_tokens,cache_miss_tokens,output_tokens,usd,lines,status,seconds,api_usd,detail\n"
        "2026-10-03 16:00:00,claude:sonnet,D-i p1-5,0,10,5,0,1000,ok,60.0,0.2,\n"
        "2026-10-03 23:00:00,claude:sonnet,D-i p6-9,0,10,5,0,2983,ok,60.0,0.2,\n", encoding="utf-8")
    calls, _, _ = stats.load_calls(ledger, tmp_path / "missing.db")
    readings = tmp_path / "usage_readings.csv"
    stats.add_reading(readings, 9, "")
    # no reset time given: the week starts with the first Claude call, so all 3,983 lines count
    t_read = datetime.now(timezone.utc)
    capacity = stats.claude_weekly_lines(calls, [(t_read, 9.0, None)])
    assert capacity == pytest.approx(3983 / 0.09)
    assert stats.read_readings(readings)[0][1] == 9.0
    assert stats.claude_weekly_lines(calls, []) is None


def test_a_late_reply_after_a_timeout_does_not_count_the_lines_twice(monkeypatch):
    import threading
    monkeypatch.setenv("DEEPSEEK_KEY_1", "d1")
    usage = {"prompt_cache_miss_tokens": 900, "completion_tokens": 50}
    attempts = []

    def chat(*a):
        attempts.append(1)
        if len(attempts) == 1:
            threading.Event().wait(0.4)  # outlives the 0.05 s timeout; time.sleep is stubbed here
            return "late", 200, "", usage
        return "ok", 200, "", usage

    monkeypatch.setattr(ai.ai_openai_compat, "chat", chat)
    assert ai.call_gemini(ai.make_rotator([]), "p", "s", models=["deepseek:deepseek-v4-flash"],
                          timeout=0.05, lines=12) == "ok"
    threading.Event().wait(0.7)  # let the abandoned worker finish and write its row

    got = rows()
    assert sorted(r["status"] for r in got) == ["ok", "ok", "timeout"]
    assert sum(int(r["lines"]) for r in got if r["status"] == "ok") == 12  # the late paid reply carries 0
    assert len(got) == 3  # the late worker adds no second failure row on top of the timeout row


def test_weekly_capacity_without_a_reset_time_ignores_older_weeks(tmp_path):
    ledger = tmp_path / "weeks.csv"
    now = datetime.now(timezone.utc)
    fmt = lambda days: (now - __import__("datetime").timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    ledger.write_text(
        "time_utc,model,label,cache_hit_tokens,cache_miss_tokens,output_tokens,usd,lines,status,seconds,api_usd,detail\n"
        f"{fmt(20)},claude:sonnet,D-i p1-5,0,10,5,0,5000,ok,60.0,0.2,\n"
        f"{fmt(1)},claude:sonnet,D-i p6-9,0,10,5,0,1000,ok,60.0,0.2,\n", encoding="utf-8")
    calls, _, _ = stats.load_calls(ledger, tmp_path / "missing.db")
    assert stats.claude_weekly_lines(calls, [(now, 10.0, None)]) == pytest.approx(10_000)


def test_claude_call_without_an_api_value_is_unknown_not_zero(tmp_path):
    costs.record("claude:sonnet", "D-i p1-5", {"completion_tokens": 9}, lines=10)
    costs.record("deepseek:deepseek-v4-flash", "D-i p6-9", {"completion_tokens": 9}, lines=10)
    claude, deepseek = rows()
    assert claude["api_usd"] == "" and deepseek["api_usd"] != ""
    calls, _, _ = stats.load_calls(costs.LEDGER, tmp_path / "missing.db")
    assert [c.api_usd is None for c in calls] == [True, False]


def test_a_mistyped_weekly_percent_is_rejected(tmp_path):
    for bad in (0, -3, 150):
        with pytest.raises(SystemExit):
            stats.add_reading(tmp_path / "usage_readings.csv", bad, "")
    assert not (tmp_path / "usage_readings.csv").exists()
