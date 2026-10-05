"""
export_text.py — write a plain text file of source Pāli and its translation,
paragraph by paragraph: the Pāli in the target language's script, then the
translation, then a blank line. Only translated paragraphs are written.
Without --book: one <lang>_<sc_id>.txt per finished sutta, e.g. kn_dn1.txt.

    uv run src/export_text.py --lang kn --out-dir exports/kn     # one file per finished sutta
    uv run src/export_text.py --lang kn --book M-i --start 280 --end 410 --out mn10_kn.txt
"""

import argparse
import glob
import os
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


def sutta_ranges(epitaka_db: str, book: str) -> list[tuple[str, int, int]]:
    """(sc_id, first para_id, last para_id) per sutta, in book order.

    Suttas sit at different heading levels per book (DN 2, MN 4), so the
    first heading of each sc_id sets that sutta's level. It ends before the
    next heading at that level or above: the next sutta, or a vagga title.
    """
    heads = _read(epitaka_db, "SELECT para_id, level, sc_id FROM headings "
                  "WHERE book_id=? ORDER BY para_id", (book,))
    seen: set[str] = set()
    out = []
    for i, (para, level, sc) in enumerate(heads):
        if not sc or sc in seen:
            continue
        seen.add(sc)
        end = next((p - 1 for p, lv, _ in heads[i + 1:] if lv <= level), 10**9)
        out.append((sc, para, end))
    return out


def export_text(epitaka_db: str, lang: str, book: str, start: int, end: int,
                script: str | None = None) -> str:
    sql = ("SELECT para_id, line_id, {col} FROM sentences "
           "WHERE book_id=? AND para_id BETWEEN ? AND ? ORDER BY para_id, line_id")
    pali = _paragraphs(_read(epitaka_db, sql.format(col="pali"), (book, start, end)))
    trans = _paragraphs(_read(cu.lang_db_path(epitaka_db, lang),
                              sql.format(col="translation"), (book, start, end)))

    pali = {p: _to_script(t, script or PALI_SCRIPTS.get(lang)) for p, t in pali.items() if p in trans}

    return "".join(f"{pali[p]}\n{trans[p]}\n\n" for p in sorted(pali))


def _line_ids(path: str, col: str, book: str, start: int, end: int) -> set[tuple[int, int]]:
    rows = _read(path, f"SELECT para_id, line_id, {col} FROM sentences WHERE book_id=? "
                       f"AND para_id BETWEEN ? AND ? AND {col} <> ''", (book, start, end))
    # Lines like "…", "–" or "+" carry nothing to translate and are left empty (D-i 424.8).
    return {(p, ln) for p, ln, text in rows if any(c.isalpha() for c in _TAG.sub("", text))}


def export_suttas(epitaka_db: str, lang: str, out_dir: str,
                  script: str | None = None) -> tuple[int, list[str]]:
    """One <lang>_<sc_id>.txt per finished sutta; returns (files written, skipped-sutta notes)."""
    lang_db = cu.lang_db_path(epitaka_db, lang)
    done = {b for (b,) in _read(lang_db, "SELECT DISTINCT book_id FROM sentences WHERE translation <> ''", ())}
    books = [b for (b,) in _read(epitaka_db, "SELECT book_id FROM books ORDER BY id", ()) if b in done]

    os.makedirs(out_dir, exist_ok=True)
    # A sutta whose file was written last time may no longer qualify.
    for old in glob.glob(os.path.join(out_dir, "*.txt")):
        os.remove(old)

    written, skipped = 0, []
    for book in books:
        for sc, start, end in sutta_ranges(epitaka_db, book):
            # Per line, not per paragraph: M-i 520 had one sentence untranslated in a translated paragraph.
            pali = _line_ids(epitaka_db, "pali", book, start, end)
            trans = _line_ids(lang_db, "translation", book, start, end) & pali
            # A Drive doc is never overwritten, so a part-done sutta uploaded now would stay part-done.
            if trans != pali:
                skipped.append(f"{sc}: {len(trans)} of {len(pali)} lines")
                continue
            with open(os.path.join(out_dir, f"{lang}_{sc}.txt"), "w", encoding="utf-8") as f:
                f.write(export_text(epitaka_db, lang, book, start, end, script))
            written += 1
    return written, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--lang", required=True, help='Translation language code, e.g. "kn".')
    ap.add_argument("--book", help='Book id, e.g. "M-i" (default: one file per finished sutta, see --out-dir).')
    ap.add_argument("--start", type=int, default=0, help="First para_id (default: book start).")
    ap.add_argument("--end", type=int, default=10**9, help="Last para_id, inclusive (default: book end).")
    ap.add_argument("--out", help="Output .txt path (with --book).")
    ap.add_argument("--out-dir", help="Folder for the per-sutta files (without --book); its old .txt files are removed.")
    ap.add_argument("--script", default=None,
                    help="Aksharamukha script for the Pāli (default: the target language's script).")
    ap.add_argument("--epitaka-db", default=cu.EPITAKA_DB)
    args = ap.parse_args()

    if args.book:
        if not args.out:
            ap.error("--book needs --out")
        text = export_text(args.epitaka_db, args.lang, args.book, args.start, args.end, args.script)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Wrote {args.out}")
        return 0

    if not args.out_dir:
        ap.error("give --book with --out, or --out-dir")
    written, skipped = export_suttas(args.epitaka_db, args.lang, args.out_dir, args.script)
    print(f"Wrote {written} files to {args.out_dir}")
    for note in skipped:
        print(f"Skipped, not finished: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
