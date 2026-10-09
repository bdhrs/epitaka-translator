"""
stats.py — read the call log (costs.csv) and print translation stats per day,
week or month, the recent working sessions, and a forecast of what is left.

    uv run src/stats.py report [day|week|month] [--lang kn]
    uv run src/stats.py usage 9 --reset "2026-10-10 22:30"

The three ways of paying are counted differently on purpose:
  - DeepSeek / OpenRouter: an API key, every call costs real money (`usd`).
  - Claude: a flat subscription. Calls cost nothing extra; what limits the work
    is the 5 h window and the weekly limit, so the forecast needs a weekly
    reading typed in by hand (`usage`), because only the Claude app shows it.
  - Gemini: the free tier. Calls cost nothing; the daily quota is the limit.
`api_usd` is what a call is worth at API prices, a yardstick for all three.
"""

import argparse
import csv
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path

from common import common_utils as cu
from common import costs

PLAN_FEE_USD = 20.0       # Claude plan, per month
IDLE_SECONDS = 600        # a longer gap before a call is not counted as work
SESSION_GAP_SECONDS = 1800  # a longer gap between ok calls starts a new session (the real log has a 12 min gap after the first call)
MIN_CALLS_TO_FORECAST = 5
PAID_PROVIDERS = {"deepseek", "openrouter", "azure"}
READINGS_FIELDS = ["time_utc", "percent", "reset_utc"]

# Same rule as book_translator.fetch_paragraphs_range: a line is worth
# translating when it has 3+ characters and is not just a number.
_NUMBER_ONLY = re.compile(r"^[\d\s.,;:()\[\]–—-]+$")
_LABEL = re.compile(r"^(\S+) p(\d+)-(\d+)(?:_L(\d+)-(\d+))?$")

SCOPES = [("Root texts", ["Mūla"]),
          ("Root texts + commentaries", ["Mūla", "Aṭṭhakathā"]),
          ("Root texts + commentaries + sub-commentaries", ["Mūla", "Aṭṭhakathā", "Ṭīkā"])]


@dataclass
class Call:
    t: datetime              # UTC
    model: str
    provider: str
    status: str              # ok / limit / error / timeout
    lines: int
    work: float              # seconds of real work this call stands for
    usd: float               # what was charged at the model's own price
    api_usd: float | None    # value at API prices; None when unknown (old Claude rows)

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def provider_of(model: str) -> str:
    return model.split(":")[0] if ":" in model else "gemini"


def translatable(pali: str | None) -> bool:
    p = (pali or "").strip()
    return len(p) >= 3 and not _NUMBER_ONLY.match(p)


def open_ro(path: str | Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def estimate_lines(db: sqlite3.Connection, label: str) -> int:
    """Lines an old ledger row covered, counted from the source text (rows before the `lines` column)."""
    m = _LABEL.match(label)
    if not m:
        return 0
    book, a, b = m.group(1), int(m.group(2)), int(m.group(3))
    lo, hi = (int(m.group(4)), int(m.group(5))) if m.group(4) and a == b else (0, 10**9)
    rows = db.execute("SELECT pali FROM sentences WHERE book_id=? AND para_id BETWEEN ? AND ? "
                      "AND line_id BETWEEN ? AND ?", (book, a, b, lo, hi))
    return sum(translatable(p) for (p,) in rows)


def load_calls(ledger: Path, source_db: Path) -> tuple[list[Call], int, int]:
    """Returns (calls, old rows whose lines were estimated, rows skipped as unreadable)."""
    if not ledger.exists():
        return [], 0, 0
    src = open_ro(source_db) if source_db.exists() else None
    cache: dict[str, int] = {}
    calls: list[Call] = []
    estimated = skipped = 0
    with open(ledger, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                t = datetime.strptime(row["time_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                model = row["model"]
                status = row.get("status") or ""
                if not status:  # old row: a call that returned no tokens was a failure (a limit hit)
                    status = "ok" if int(row["output_tokens"] or 0) > 0 else "limit"
                lines = int(row["lines"]) if row.get("lines") else 0
                if not row.get("lines") and status == "ok" and src is not None:
                    if row["label"] not in cache:
                        cache[row["label"]] = estimate_lines(src, row["label"])
                    lines = cache[row["label"]]
                    estimated += lines > 0
                usd = float(row["usd"])
                prov = provider_of(model)
                if row.get("api_usd"):
                    api_usd = float(row["api_usd"])
                else:
                    api_usd = usd if prov != "claude" else None
                calls.append(Call(t, model, prov, status, lines,
                                  float(row.get("seconds") or 0), usd, api_usd))
            except (KeyError, ValueError):
                skipped += 1
    if src is not None:
        src.close()
    calls.sort(key=lambda c: c.t)
    _assign_work(calls)
    return calls, estimated, skipped


def _assign_work(calls: list[Call]) -> None:
    """Set each ok call's work time: its own duration if logged, else the gap since the model's previous call."""
    prev: dict[str, datetime] = {}
    for c in calls:
        before = prev.get(c.model)
        prev[c.model] = c.t
        if not c.ok:
            continue
        if c.work > 0:
            continue
        gap = (c.t - before).total_seconds() if before else 0
        c.work = gap if 0 < gap <= IDLE_SECONDS else 0


def _money(x: float | None) -> str:
    return "n/a" if x is None else f"${x:,.2f}"


def _hm(seconds: float) -> str:
    return f"{int(seconds // 3600)}h{int(seconds % 3600 // 60):02d}m"


def _paid(provider: str, usd: float) -> str:
    if provider in PAID_PROVIDERS:
        return _money(usd)
    return "plan" if provider == "claude" else "free"


def bucket_of(t: datetime, period: str, tz: tzinfo) -> str:
    d = t.astimezone(tz).date()
    if period == "day":
        return d.isoformat()
    if period == "week":
        return f"week of {(d - timedelta(days=d.weekday())).isoformat()}"
    return d.strftime("%Y-%m")


def _table(header: list[str], rows: list[list[str]], left: int = 2) -> str:
    """Plain aligned columns; the first `left` columns are left-aligned, the rest right-aligned."""
    widths = [max(len(r[i]) for r in [header] + rows) for i in range(len(header))]
    def fmt(r):
        return "  ".join(r[i].ljust(widths[i]) if i < left else r[i].rjust(widths[i]) for i in range(len(r)))
    return "\n".join([fmt(header), "  ".join("-" * w for w in widths)] + [fmt(r) for r in rows])


def _sums(calls: list[Call]) -> list[str]:
    ok = [c for c in calls if c.ok]
    lines, work = sum(c.lines for c in ok), sum(c.work for c in ok)
    known = [c.api_usd for c in calls if c.api_usd is not None]
    return [str(len(ok)), str(len(calls) - len(ok)), f"{lines:,}", _hm(work),
            f"{lines / (work / 3600):,.0f}" if work else "-",
            _money(sum(known) if known else None),
            _paid(calls[0].provider, sum(c.usd for c in calls))]


COLUMNS = ["Calls ok", "Failed", "Lines", "Work", "Lines/h", "API value", "You paid"]


def period_report(calls: list[Call], period: str, tz: tzinfo, last: int) -> str:
    groups: dict[tuple[str, str], list[Call]] = defaultdict(list)
    for c in calls:
        groups[(bucket_of(c.t, period, tz), c.model)].append(c)
    buckets = sorted({k[0] for k in groups})[-last:]
    rows = [[b, m] + _sums(groups[(b, m)]) for b in buckets for m in sorted({k[1] for k in groups if k[0] == b})]
    by_model: dict[str, list[Call]] = defaultdict(list)
    for c in calls:
        by_model[c.model].append(c)
    totals = [["All time", m] + _sums(cs) for m, cs in sorted(by_model.items())]
    return _table([period.capitalize(), "Model"] + COLUMNS, rows) + "\n\n" + \
        _table(["", "Model"] + COLUMNS, totals)


@dataclass
class Session:
    model: str
    start: datetime
    last_ok: datetime
    calls: int = 0
    lines: int = 0
    work: float = 0.0
    ended: str = "-"


def sessions(calls: list[Call]) -> list[Session]:
    """A run of ok calls with no gap over SESSION_GAP_SECONDS; for Claude this is one usage window."""
    out: list[Session] = []
    cur: dict[str, Session] = {}
    for c in calls:
        s = cur.get(c.model)
        if c.ok:
            if s is None or (c.t - s.last_ok).total_seconds() > SESSION_GAP_SECONDS:
                s = cur[c.model] = Session(c.model, c.t, c.t)
                out.append(s)
            s.calls += 1
            s.lines += c.lines
            s.work += c.work
            s.last_ok = c.t
            s.ended = "-"  # a retry that worked means the earlier failure did not end the session
        elif s is not None:
            s.ended = "limit" if c.status == "limit" else (s.ended if s.ended == "limit" else "error")
    return out


def session_report(calls: list[Call], tz: tzinfo, last: int) -> str:
    ss = sorted(sessions(calls), key=lambda s: s.start)[-last:]
    rows = [[s.start.astimezone(tz).strftime("%Y-%m-%d %H:%M"), s.model, str(s.calls),
             f"{s.lines:,}", _hm(s.work), s.ended] for s in ss]
    return _table(["Start", "Model", "Calls", "Lines", "Work", "Ended by"], rows, left=2)


def read_readings(path: Path) -> list[tuple[datetime, float, datetime | None]]:
    if not path.exists():
        return []
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            parse = lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            out.append((parse(r["time_utc"]), float(r["percent"]), parse(r["reset_utc"]) if r["reset_utc"] else None))
    return sorted(out)


def claude_weekly_lines(calls: list[Call], readings) -> float | None:
    """Lines a full Claude week allows: lines done this week divided by the weekly percent used."""
    if not readings:
        return None
    t_read, percent, reset = readings[-1]
    ok = [c for c in calls if c.provider == "claude" and c.ok]
    if percent <= 0 or not ok:
        return None
    # Without a reset time, assume the week is the 7 days before the reading.
    start = reset - timedelta(days=7) if reset else max(ok[0].t, t_read - timedelta(days=7))
    done = sum(c.lines for c in ok if start <= c.t <= t_read)
    return done / (percent / 100) if done else None


def pending_by_category(epitaka_db: Path, lang_db: Path) -> Counter:
    """Untranslated lines of the Sutta and Vinaya books, by Mūla / Aṭṭhakathā / Ṭīkā."""
    done: set[tuple[str, int, int]] = set()
    if lang_db.exists():
        with open_ro(lang_db) as conn:
            done = set(conn.execute("SELECT book_id, para_id, line_id FROM sentences "
                                    "WHERE translation IS NOT NULL AND translation != ''"))
    counts: Counter = Counter()
    with open_ro(epitaka_db) as conn:
        for cat, book, para, line, pali in conn.execute(
                "SELECT b.category, s.book_id, s.para_id, s.line_id, s.pali FROM sentences s "
                "JOIN books b ON b.book_id = s.book_id "
                "WHERE b.nikaya IN ('Sutta Piṭaka', 'Vinaya Piṭaka')"):
            if translatable(pali) and (book, para, line) not in done:
                counts[cat] += 1
    return counts


def _recent_rate(calls: list[Call], tz: tzinfo, days: int = 7) -> tuple[float, float, float, int]:
    """(lines per work hour, usd per line, lines per active day, ok calls) over the last `days` days, else all time."""
    ok = [c for c in calls if c.ok and c.lines > 0]
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent = [c for c in ok if c.t >= cutoff]
    use = recent if len(recent) >= 5 else ok
    lines, work = sum(c.lines for c in use), sum(c.work for c in use)
    active_days = len({c.t.astimezone(tz).date() for c in use})
    return (lines / (work / 3600) if work else 0.0,
            sum(c.usd for c in use) / lines if lines else 0.0,
            lines / active_days if active_days else 0.0,
            len(use))


def forecast(calls: list[Call], pending: Counter, readings, tz: tzinfo) -> str:
    out = []
    lefts = [(name, sum(pending[c] for c in cats)) for name, cats in SCOPES]
    for prov in sorted({c.provider for c in calls}):
        pc = [c for c in calls if c.provider == prov]
        lph, usd_line, per_day, n = _recent_rate(pc, tz)
        if n < MIN_CALLS_TO_FORECAST:
            out.append(f"\n{prov}: only {n} ok calls so far, too few to forecast.")
            continue
        out.append(f"\n{prov} ({n} recent ok calls, {lph:,.0f} lines per work hour):")
        rows = []
        for name, left in lefts:
            if prov in PAID_PROVIDERS:
                hours = left / lph if lph else 0
                rows.append([name, f"{left:,}", f"{hours:,.0f}h non-stop ({hours / 24:.1f} days)",
                             _money(left * usd_line)])
            elif prov == "claude":
                week = claude_weekly_lines(pc, readings)
                if week is None:
                    rows.append([name, f"{left:,}", "needs a weekly reading: just usage <percent> <reset>", "plan"])
                else:
                    weeks = left / week
                    rows.append([name, f"{left:,}", f"{weeks:.1f} weeks ({week:,.0f} lines a week)",
                                 f"plan: {_money(weeks * 12 / 52 * PLAN_FEE_USD)} if bought only for this"])
            else:
                days = left / per_day if per_day else 0
                rows.append([name, f"{left:,}", f"{days:,.0f} active days ({per_day:,.0f} lines a day)", "free"])
        out.append(_table(["Scope", "Lines left", "Time", "Cost"], rows, left=4))
    return "\n".join(out)


def add_reading(path: Path, percent: float, reset_local: str) -> None:
    if not 0 < percent <= 100:
        raise SystemExit(f"percent must be between 0 and 100, got {percent:g}")
    reset = ""
    if reset_local:
        reset = datetime.strptime(reset_local, "%Y-%m-%d %H:%M").astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(READINGS_FIELDS)
        w.writerow([datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), percent, reset])
    print(f"Saved: {percent:g}% of the weekly limit used"
          + (f", week resets {reset_local} (local)." if reset_local else ". No reset time given, so the week is assumed to be the 7 days before now."))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("report", help="print the stats")
    rp.add_argument("period", nargs="?", default="day", choices=["day", "week", "month"])
    rp.add_argument("--lang", default="kn")
    rp.add_argument("--last", type=int, default=0, help="how many periods to show (default 14 days, 8 weeks, 12 months)")
    rp.add_argument("--sessions", type=int, default=10, help="how many recent working sessions to show")
    rp.add_argument("--no-forecast", action="store_true", help="skip counting the lines left (takes a few seconds)")
    up = sub.add_parser("usage", help="save a weekly Claude usage reading")
    up.add_argument("percent", type=float, help="the weekly percent shown by /usage")
    up.add_argument("--reset", default="", help='when the week resets, local time, "YYYY-MM-DD HH:MM"')
    args = ap.parse_args(argv)

    readings_path = costs.LEDGER.parent / "usage_readings.csv"
    if args.cmd == "usage":
        add_reading(readings_path, args.percent, args.reset)
        return 0

    tz = datetime.now().astimezone().tzinfo or timezone.utc
    epitaka_db = Path(cu.EPITAKA_DB)
    calls, estimated, skipped = load_calls(costs.LEDGER, epitaka_db)
    if not calls:
        print(f"No calls in {costs.LEDGER} yet.")
        return 1
    print(f"{len(calls):,} calls from {calls[0].t.astimezone(tz):%Y-%m-%d %H:%M} to "
          f"{calls[-1].t.astimezone(tz):%Y-%m-%d %H:%M} (times are local, {tz}).")
    if estimated:
        print(f"{estimated:,} old calls had no line count: lines were counted from the source text (about right).")
        print("Old calls had no outcome either: one with no tokens counts as a limit hit.")
    if skipped:
        print(f"WARNING: {skipped} unreadable ledger rows were skipped.")
    print()

    last = args.last or {"day": 14, "week": 8, "month": 12}[args.period]
    print(period_report(calls, args.period, tz, last))
    print("\nRecent working sessions (for Claude, one session is one usage window):")
    print(session_report(calls, tz, args.sessions))

    if not args.no_forecast:
        lang_db = Path(cu.lang_db_path(str(epitaka_db), args.lang))
        pending = pending_by_category(epitaka_db, lang_db)
        print(f"\nWhat is left for {args.lang} (Sutta and Vinaya books), and how long it would take at the recent rate:")
        print(forecast(calls, pending, read_readings(readings_path), tz))
    return 0


if __name__ == "__main__":
    sys.exit(main())
