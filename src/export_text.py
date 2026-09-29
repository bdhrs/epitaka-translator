"""
export_text.py — write a plain text file of source Pāli and its translation,
paragraph by paragraph: the Pāli in the target language's script, then the
translation, then a blank line. Only translated paragraphs are written.

    uv run src/export_text.py --lang kn --out kn.txt            # everything so far, canon order
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
_BOOK_CODE = re.compile(r"^[A-Z]{2}\d+-")


def _ascii_digits(text: str) -> str:
    """೧೦೫ -> 105: Aksharamukha converts digits too; the user wants 0-9 (2026-09-28)."""
    return "".join(str(unicodedata.digit(c)) if c.isdigit() else c for c in text)


def _to_script(text: str, script: str | None) -> str:
    """Roman Pāli -> the given Aksharamukha script (ASCII digits); unchanged when no script."""
    if not script:
        return text
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)  # noisy on first import
        from aksharamukha import transliterate
    return _ascii_digits(transliterate.process("IASTPali", script, text))


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

    pali = {p: _to_script(t, script or PALI_SCRIPTS.get(lang)) for p, t in pali.items() if p in trans}

    return "".join(f"{pali[p]}\n{trans[p]}\n\n" for p in sorted(pali))


def export_all(epitaka_db: str, lang: str, script: str | None = None) -> str:
    """Every book with any translation, in canon order, each under its name."""
    done = {b for (b,) in _read(cu.lang_db_path(epitaka_db, lang),
                                "SELECT DISTINCT book_id FROM sentences WHERE translation <> ''", ())}
    books = _read(epitaka_db, "SELECT book_id, book_name FROM books ORDER BY id", ())
    script = script or PALI_SCRIPTS.get(lang)
    return "".join(
        # "MN1-Mūlapaṇṇāsapāḷi" -> "Mūlapaṇṇāsapāḷi": the reader sees only the target script.
        _to_script(_BOOK_CODE.sub("", name or book), script) + "\n\n"
        + export_text(epitaka_db, lang, book, 0, 10**9, script)
        for book, name in books if book in done
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--lang", required=True, help='Translation language code, e.g. "kn".')
    ap.add_argument("--book", help='Book id, e.g. "M-i" (default: every translated book).')
    ap.add_argument("--start", type=int, default=0, help="First para_id (default: book start).")
    ap.add_argument("--end", type=int, default=10**9, help="Last para_id, inclusive (default: book end).")
    ap.add_argument("--out", required=True, help="Output .txt path.")
    ap.add_argument("--script", default=None,
                    help="Aksharamukha script for the Pāli (default: the target language's script).")
    ap.add_argument("--epitaka-db", default=cu.EPITAKA_DB)
    args = ap.parse_args()

    if args.book:
        text = export_text(args.epitaka_db, args.lang, args.book, args.start, args.end, args.script)
    else:
        text = export_all(args.epitaka_db, args.lang, args.script)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
