"""
export_text.py — write a plain text file of source Pāli and its translation,
paragraph by paragraph: the Pāli in the target language's script, then the
translation, then a blank line.

    uv run src/export_text.py --lang kn --book M-i --start 280 --end 410 --out mn10_kn.txt
"""

import argparse
import re
import sqlite3
import sys
import unicodedata
import warnings
from collections import defaultdict

import common.common_utils as cu

# Aksharamukha script names for target languages; anything else stays Roman.
PALI_SCRIPTS = {
    "kn": "Kannada", "te": "Telugu", "ta": "Tamil", "ml": "Malayalam",
    "hi": "Devanagari", "mr": "Devanagari", "ne": "Devanagari",
    "bn": "Bengali", "gu": "Gujarati", "pa": "Gurmukhi", "or": "Oriya",
    "si": "Sinhala", "th": "Thai", "my": "Burmese",
}

_TAG = re.compile(r"<[^>]+>")


def _ascii_digits(text: str) -> str:
    """೧೦೫ -> 105: Aksharamukha converts digits too; the user wants 0-9 (2026-09-28)."""
    return "".join(str(unicodedata.digit(c)) if c.isdigit() else c for c in text)


def _read(path: str, sql: str, args: tuple) -> list[tuple]:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        return conn.execute(sql, args).fetchall()


def _paragraphs(rows: list[tuple]) -> dict[int, str]:
    paras: dict[int, list[str]] = defaultdict(list)
    for para_id, _line_id, text in rows:
        if text:
            paras[para_id].append(_TAG.sub("", text).strip())
    return {p: " ".join(lines) for p, lines in paras.items()}


def export_text(epitaka_db: str, lang: str, book: str, start: int, end: int,
                script: str | None = None) -> str:
    sql = ("SELECT para_id, line_id, {col} FROM sentences "
           "WHERE book_id=? AND para_id BETWEEN ? AND ? ORDER BY para_id, line_id")
    pali = _paragraphs(_read(epitaka_db, sql.format(col="pali"), (book, start, end)))
    trans = _paragraphs(_read(cu.lang_db_path(epitaka_db, lang),
                              sql.format(col="translation"), (book, start, end)))

    script = script or PALI_SCRIPTS.get(lang)
    if script:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)  # noisy on first import
            from aksharamukha import transliterate
        pali = {p: _ascii_digits(transliterate.process("IASTPali", script, t))
                for p, t in pali.items()}

    return "".join(f"{pali[p]}\n{trans.get(p, '')}\n\n" for p in sorted(pali))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--lang", required=True, help='Translation language code, e.g. "kn".')
    ap.add_argument("--book", required=True, help='Book id, e.g. "M-i".')
    ap.add_argument("--start", type=int, required=True, help="First para_id.")
    ap.add_argument("--end", type=int, required=True, help="Last para_id (inclusive).")
    ap.add_argument("--out", required=True, help="Output .txt path.")
    ap.add_argument("--script", default=None,
                    help="Aksharamukha script for the Pāli (default: the target language's script).")
    ap.add_argument("--epitaka-db", default=cu.EPITAKA_DB)
    args = ap.parse_args()

    text = export_text(args.epitaka_db, args.lang, args.book, args.start, args.end, args.script)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Wrote {text.count(chr(10) * 2)} paragraphs to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
