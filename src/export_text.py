"""
export_text.py — write a plain text file of source Pāli and its translation,
paragraph by paragraph: the Pāli in the target language's script, a blank line,
the translation, then the review remarks if any. Only translated paragraphs are written.
Without --book: one file per finished book in <out-dir>/<lang>/<nikaya>/, e.g. kn/01_Digha_Nikaya/01_D-i.txt.

    uv run src/export_text.py --lang kn --out-dir exports        # one file per finished book
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
    out = transliterate.process("IASTPali", script, text)
    if out is None:
        raise ValueError(f"aksharamukha returned nothing for script {script!r}")
    return _ascii_digits(out)


def _read(path: str, sql: str, args: tuple) -> list[tuple]:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        return conn.execute(sql, args).fetchall()


def _paragraphs(rows: list[tuple]) -> dict[int, str]:
    paras: dict[int, list[str]] = defaultdict(list)
    for para_id, _, text in rows:
        if text:
            paras[para_id].append(_TAG.sub("", text).strip())
    return {p: " ".join(lines) for p, lines in paras.items()}


_SEVERITY_KAN = {"wrong": "ತಪ್ಪು", "critical": "ಗಂಭೀರ"}


def _remarks_for_range(lang_db: str, book: str, start: int, end: int) -> dict[int, list[tuple]]:
    """Review remarks (verify_translation.py) by para_id; none when the table is missing.

    Review remarks carry their severity in `note`; the translator's own remarks
    (older rows) put an explanation there, so they are left out.
    """
    if not _read(lang_db, "SELECT 1 FROM sqlite_master WHERE name='translation_remarks'", ()):
        return {}
    rows = _read(lang_db, "SELECT para_id, line_id, note, conflict, translation FROM translation_remarks "
                          "WHERE book_id=? AND para_id BETWEEN ? AND ? AND note IN ('wrong', 'critical') "
                          "ORDER BY para_id, line_id, id", (book, start, end))
    out: dict[int, list[tuple]] = defaultdict(list)
    for para_id, *rest in rows:
        out[para_id].append(tuple(rest))
    return dict(out)


def _remark_annotation(remarks: list[tuple]) -> str:
    """One paragraph's review remarks as a block, with the reviewer's text exactly as written."""
    if not remarks:
        return ""
    lines = ["ಪರಿಶೀಲನಾ ಟಿಪ್ಪಣಿಗಳು:"]
    for line_id, severity, explanation, suggestion in remarks:
        lines.append(f"  ಲೈನ್ {line_id} [{_SEVERITY_KAN[severity]}]: {(explanation or '').strip()}")
        if (suggestion or "").strip():
            lines.append(f"    ಸೂಚಿತ ತಿದ್ದುಪಡಿ: {suggestion.strip()}")
    return "\n\n" + "\n".join(lines)


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
                script: str | None = None, remarks: bool = True) -> str:
    sql = ("SELECT para_id, line_id, {col} FROM sentences "
           "WHERE book_id=? AND para_id BETWEEN ? AND ? ORDER BY para_id, line_id")
    pali = _paragraphs(_read(epitaka_db, sql.format(col="pali"), (book, start, end)))
    trans = _paragraphs(_read(cu.lang_db_path(epitaka_db, lang),
                              sql.format(col="translation"), (book, start, end)))

    script = script or PALI_SCRIPTS.get(lang)
    pali = {p: _to_script(t, script) for p, t in pali.items() if p in trans}

    notes = _remarks_for_range(cu.lang_db_path(epitaka_db, lang), book, start, end) if remarks else {}

    return "".join(
        f"{pali[p]}\n\n{trans[p]}{_remark_annotation(notes.get(p, []))}\n\n\n"
        for p in sorted(pali)
    )


def _line_ids(path: str, col: str, book: str, start: int, end: int) -> set[tuple[int, int]]:
    rows = _read(path, f"SELECT para_id, line_id, {col} FROM sentences WHERE book_id=? "
                       f"AND para_id BETWEEN ? AND ? AND {col} <> ''", (book, start, end))
    # Lines like "…", "–" or "+" carry nothing to translate and are left empty (D-i 424.8).
    return {(p, ln) for p, ln, text in rows if any(c.isalpha() for c in _TAG.sub("", text))}


def _ascii(name: str) -> str:
    """The name without accents and with only letters, digits, "_" and "-": "Dīgha Nikāya" -> "Digha_Nikaya"."""
    folded = "".join(c for c in unicodedata.normalize("NFD", name) if not unicodedata.combining(c))
    return re.sub(r"[^\w-]+", "_", folded).strip("_")


README_NAME = "!!! README FIRST.txt"  # the "!!!" sorts it first on Drive
README_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "readme_first.txt")

# A Google Doc holds about 1,020,000 characters; stay clear of it.
GOOGLE_DOC_LIMIT = 1_020_000
MAX_FILE_CHARS = 900_000


def _readme_text(lang: str) -> str:
    """The template with the language name without its native-script bracket: "Kannada"."""
    with open(README_TEMPLATE, encoding="utf-8") as f:
        return f.read().replace("{language}", cu.lang_name(lang).split(" (")[0])


def write_readme(lang_dir: str, lang: str) -> None:
    """Write the proofreaders' instructions into a language folder."""
    text = _readme_text(lang)
    with open(os.path.join(lang_dir, README_NAME), "w", encoding="utf-8") as f:
        f.write(text)


def _parts(texts: list[str]) -> list[str]:
    """Join whole suttas into files of at most MAX_FILE_CHARS; a sutta is never cut in two."""
    parts: list[list[str]] = [[]]
    size = 0
    for t in texts:
        if parts[-1] and size + len(t) > MAX_FILE_CHARS:
            parts.append([])
            size = 0
        parts[-1].append(t)
        size += len(t)
    return ["".join(p) for p in parts]


def _sutta_texts(epitaka_db: str, lang: str, book: str, start: int, end: int,
                 script: str | None, remarks: bool) -> list[str]:
    """The sutta's text, in pieces when it is too big for one file.

    A piece is cut only before a heading inside the sutta: first before the
    highest-level headings, then, if a piece is still too big, before the next
    level down. A piece with no heading left inside stays whole.
    """
    text = export_text(epitaka_db, lang, book, start, end, script, remarks)
    if len(text) <= MAX_FILE_CHARS:
        return [text]
    inner = _read(epitaka_db, "SELECT para_id, level FROM headings WHERE book_id=? AND para_id>? AND para_id<=? "
                              "AND level<10 ORDER BY para_id", (book, start, end))
    if not inner:
        return [text]
    top = min(level for _, level in inner)
    cuts = [start] + [para for para, level in inner if level == top] + [end + 1]
    pieces: list[str] = []
    for a, b in zip(cuts, cuts[1:]):
        pieces += _sutta_texts(epitaka_db, lang, book, a, b - 1, script, remarks)
    return pieces


def export_suttas(epitaka_db: str, lang: str, out_dir: str,
                  script: str | None = None, remarks: bool = True) -> tuple[int, list[str]]:
    """One file per finished book (more when it is too big), in <out_dir>/<lang>/<nikaya>/.

    The language is only the folder name, never part of a file name. Folders and
    files carry a number prefix (kn/01_Digha_Nikaya/01_D-i.txt) so they sort in
    canon order. A book too big for one Google Doc becomes 01_D-i_1.txt, 01_D-i_2.txt,
    cut between suttas, or before a heading inside a sutta that is itself too big.
    The language folder also gets README_NAME, the same text for every language.
    Returns (book files written, skipped-sutta notes).
    """
    lang_db = cu.lang_db_path(epitaka_db, lang)
    done = {b for (b,) in _read(lang_db, "SELECT DISTINCT book_id FROM sentences WHERE translation <> ''", ())}
    books = [(b, _ascii(sub or nik or "Other")) for b, sub, nik in
             _read(epitaka_db, "SELECT book_id, sub_nikaya, nikaya FROM books ORDER BY id", ()) if b in done]
    folders = {name: i for i, name in enumerate(dict.fromkeys(name for _, name in books), 1)}

    _readme_text(lang)  # fail before the old export is deleted if the template is missing
    out_dir = os.path.join(out_dir, lang)
    os.makedirs(out_dir, exist_ok=True)
    # A book whose file was written last time may have changed its parts.
    for old in glob.glob(os.path.join(out_dir, "**", "*.txt"), recursive=True):
        os.remove(old)
    for d, _, _ in os.walk(out_dir, topdown=False):
        if d != out_dir and not os.listdir(d):
            os.rmdir(d)

    write_readme(out_dir, lang)

    written, skipped = 0, []
    numbers: dict[str, int] = defaultdict(int)
    for book, folder in books:
        texts = []
        covered = 0  # a sutta nested in an earlier one is already in the book file
        for sc, start, end in sutta_ranges(epitaka_db, book):
            if end <= covered:
                continue
            start = max(start, covered + 1)
            # Per line, not per paragraph: M-i 520 had one sentence untranslated in a translated paragraph.
            pali = _line_ids(epitaka_db, "pali", book, start, end)
            trans = _line_ids(lang_db, "translation", book, start, end) & pali
            # A Drive doc is never overwritten, so a part-done sutta uploaded now would stay part-done.
            if trans != pali:
                skipped.append(f"{sc}: {len(trans)} of {len(pali)} lines")
                continue
            texts += _sutta_texts(epitaka_db, lang, book, start, end, script, remarks)
            covered = end
        if not texts:
            continue
        numbers[folder] += 1
        sub = os.path.join(out_dir, f"{folders[folder]:02d}_{folder}")
        os.makedirs(sub, exist_ok=True)
        parts = _parts(texts)
        for i, text in enumerate(parts, 1):
            suffix = f"_{i}" if len(parts) > 1 else ""
            name = f"{numbers[folder]:02d}_{_ascii(book)}{suffix}.txt"
            if len(text) > GOOGLE_DOC_LIMIT:  # a sutta with no heading inside it cannot be cut
                print(f"WARNING: {name} has {len(text):,} characters, over the Google Doc limit of {GOOGLE_DOC_LIMIT:,}.")
            with open(os.path.join(sub, name), "w", encoding="utf-8") as f:
                f.write(text)
            written += 1
    return written, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").strip().partition("\n")[0])
    ap.add_argument("--lang", required=True, help='Translation language code, e.g. "kn".')
    ap.add_argument("--book", help='Book id, e.g. "M-i" (default: one file per finished book, see --out-dir).')
    ap.add_argument("--start", type=int, default=0, help="First para_id (default: book start).")
    ap.add_argument("--end", type=int, default=10**9, help="Last para_id, inclusive (default: book end).")
    ap.add_argument("--out", help="Output .txt path (with --book).")
    ap.add_argument("--out-dir", help="Folder that holds the <lang> folder of per-book files (without --book); old .txt files under <lang> are removed.")
    ap.add_argument("--script", default=None,
                    help="Aksharamukha script for the Pāli (default: the target language's script).")
    ap.add_argument("--no-remarks", action="store_true",
                    help="Leave out the review remarks (from verify_translation.py) under each paragraph.")
    ap.add_argument("--epitaka-db", default=cu.EPITAKA_DB)
    args = ap.parse_args()

    if args.book:
        if not args.out:
            ap.error("--book needs --out")
        text = export_text(args.epitaka_db, args.lang, args.book, args.start, args.end, args.script, not args.no_remarks)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Wrote {args.out}")
        return 0

    if not args.out_dir:
        ap.error("give --book with --out, or --out-dir")
    written, skipped = export_suttas(args.epitaka_db, args.lang, args.out_dir, args.script, not args.no_remarks)
    print(f"Wrote {written} files to {args.out_dir}")
    for note in skipped:
        print(f"Skipped, not finished: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
