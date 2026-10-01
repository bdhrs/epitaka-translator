"""
compare_models.py — run one section of a book through several models and
export each result, so the translations can be read side by side.

Each model works in its own scratch folder under data/compare/, so the real
epitaka.db (the translator writes to it) and the real language database are
never touched. Each model is pinned: no fallback to another model.

    uv run src/compare_models.py --lang kn --book D-i --start 971 --end 978 \
        --models gemini-3.7-flash,gemini-3.1-pro-preview,gemini-3.8-flash
"""

import argparse
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def prepare_scratch(data_dir: Path, scratch: Path, lang: str) -> list[Path]:
    """Build a scratch data folder; return the real files that were linked, not copied."""
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    # The translator writes to these two, so each model gets its own copy.
    copied = {"epitaka.db", f"glossary_{lang}.db"}
    # Left out so every model starts from an empty translation table.
    skipped = {f"epitaka_{lang}.db"}
    linked = []
    for f in sorted(data_dir.glob("*.db")):
        if f.name in skipped:
            continue
        if f.name in copied:
            shutil.copyfile(f, scratch / f.name)
        else:
            (scratch / f.name).symlink_to(f.resolve())
            linked.append(f)
    return linked


def count_translated(lang_db: Path) -> int:
    if not lang_db.exists():
        return 0
    with sqlite3.connect(lang_db) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM sentences WHERE translation IS NOT NULL AND translation != ''"
        ).fetchone()[0]


def run_model(model: str, args, out_dir: Path) -> Path | None:
    scratch = out_dir / model.replace(":", "_").replace("/", "_")
    # A model name like ".." would make the scratch folder the data folder, and it gets deleted.
    if scratch.resolve().parent != out_dir.resolve():
        raise SystemExit(f"Refusing model name {model!r}: its scratch folder would not sit inside {out_dir}.")
    result = out_dir / f"{scratch.name}.txt"
    result.unlink(missing_ok=True)  # an old result must not pass for this run's
    linked = prepare_scratch(DATA_DIR, scratch, args.lang)
    mtimes = {f: f.stat().st_mtime_ns for f in linked}
    print(f"\n===== {model} =====", flush=True)
    try:
        run = subprocess.run(
            [sys.executable, "-u", "src/book_translator.py",
             "--lang", args.lang, "--books", args.book,
             "--start", str(args.start), "--end", str(args.end),
             "--max-parts", "1", "--model", model,
             "--epitaka-db", str(scratch / "epitaka.db")],
            cwd=ROOT,
        )
        changed = [f.name for f in linked if f.stat().st_mtime_ns != mtimes[f]]
        if changed:
            print(f"WARNING: real files changed during the {model} run: {', '.join(changed)}")

        if run.returncode != 0:
            print(f"FAILED: {model} ended with an error (exit code {run.returncode}); "
                  f"any partial translation is not exported.")
            return None
        if count_translated(scratch / f"epitaka_{args.lang}.db") == 0:
            print(f"FAILED: {model} saved no translation (model busy, out of quota, or an error).")
            return None
        export = subprocess.run(
            [sys.executable, "src/export_text.py", "--lang", args.lang,
             "--book", args.book, "--start", str(args.start), "--end", str(args.end),
             "--epitaka-db", str(scratch / "epitaka.db"), "--out", str(result)],
            cwd=ROOT,
        )
        if export.returncode != 0:
            print(f"FAILED: the export for {model} ended with an error (exit code {export.returncode}).")
            result.unlink(missing_ok=True)
            return None
        return result
    finally:
        shutil.rmtree(scratch)


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").strip().split("\n")[0])
    ap.add_argument("--lang", required=True)
    ap.add_argument("--book", required=True, help='Book id, e.g. "D-i".')
    ap.add_argument("--start", type=int, required=True, help="First para_id.")
    ap.add_argument("--end", type=int, required=True, help="Last para_id.")
    ap.add_argument("--models", required=True, help="Comma-separated models, run in this order.")
    args = ap.parse_args()

    out_dir = DATA_DIR / "compare"
    out_dir.mkdir(exist_ok=True)
    results = {m: run_model(m, args, out_dir)
               for m in (m.strip() for m in args.models.split(",")) if m}

    print("\n===== Summary =====")
    for model, path in results.items():
        print(f"{model}: {path if path else 'FAILED, no file written'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
