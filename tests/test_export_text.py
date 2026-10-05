import sqlite3

import export_text


def make_db(path, col, rows):
    with sqlite3.connect(path) as conn:
        conn.execute(f"CREATE TABLE sentences (book_id TEXT, para_id INT, line_id INT, {col} TEXT)")
        conn.executemany("INSERT INTO sentences VALUES (?,?,?,?)", rows)


def test_pali_in_kannada_then_translation(tmp_path):
    src = tmp_path / "epitaka.db"
    make_db(src, "pali", [
        ("M-i", 281, 1, "105. Evaṃ me sutaṃ"),
        ("M-i", 281, 2, "<b>bhagavā</b>"),
        ("M-i", 282, 1, "Tatra kho"),
    ])
    make_db(tmp_path / "epitaka_kn.db", "translation", [
        ("M-i", 281, 1, "ನಾನು ಹೀಗೆ ಕೇಳಿದೆನು"),
    ])

    text = export_text.export_text(str(src), "kn", "M-i", 280, 410)

    assert text == (
        "105. ಏವಂ ಮೇ ಸುತಂ ಭಗವಾ\n"
        "ನಾನು ಹೀಗೆ ಕೇಳಿದೆನು\n"
        "\n"
    )  # para 282 has no translation yet, so it is left out


def make_headings(path, rows):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE headings (book_id TEXT, para_id INT, level INT, title TEXT, sc_id TEXT)")
        conn.executemany("INSERT INTO headings VALUES (?,?,?,?,?)", rows)


# Real rows from data/epitaka.db (2026-10-05), trimmed.
HEADINGS = [
    ("D-i", 3, 1, "(DN) Sīlakkhandhavaggapāḷi", None),
    ("D-i", 4, 2, "1. Brahmajālasuttaṃ", "dn1"),
    ("D-i", 5, 4, "Paribbājakakathā", "dn1"),
    ("D-i", 208, 4, "Vivaṭṭakathādi", "dn1"),
    ("D-i", 217, 2, "2. Sāmaññaphalasuttaṃ", "dn2"),
    ("M-i", 3, 1, "(MN)Mūlapaṇṇāsapāḷi", None),
    ("M-i", 4, 2, "1. Mūlapariyāyavaggo", None),
    ("M-i", 5, 4, "1. Mūlapariyāyasuttaṃ", "mn1"),
    ("M-i", 6, 10, "1", None),
    ("M-i", 55, 4, "2. Sabbāsavasuttaṃ", "mn2"),
    ("M-i", 59, 5, "Dassanā pahātabbāsavā", "mn2"),
    ("M-i", 95, 4, "3. Dhammadāyādasuttaṃ", "mn3"),
    ("M-i", 280, 4, "10. Mahāsatipaṭṭhānasuttaṃ", "mn10"),
    ("M-i", 415, 2, "2. Sīhanādavaggo", None),
    ("M-i", 416, 4, "1. Cūḷasīhanādasuttaṃ", "mn11"),
]


def test_dn_suttas_run_to_the_next_sutta_or_book_end(tmp_path):
    db = tmp_path / "epitaka.db"
    make_headings(db, HEADINGS)

    assert export_text.sutta_ranges(str(db), "D-i") == [
        ("dn1", 4, 216), ("dn2", 217, 10**9),
    ]  # level-4 subsections stay inside dn1; book title (para 3) is in no sutta


def test_mn_suttas_skip_subsections_and_stop_at_vagga_titles(tmp_path):
    db = tmp_path / "epitaka.db"
    make_headings(db, HEADINGS)

    assert export_text.sutta_ranges(str(db), "M-i") == [
        ("mn1", 5, 54), ("mn2", 55, 94), ("mn3", 95, 279),
        ("mn10", 280, 414), ("mn11", 416, 10**9),
    ]  # para-number rows (level 10) and mn2's level-5 sections don't end a sutta


def make_sutta_dbs(tmp_path, translated):
    src = tmp_path / "epitaka.db"
    make_db(src, "pali", [  # real D-i lines
        ("D-i", 4, 1, "1. Brahmajālasuttaṃ"),
        ("D-i", 5, 1, "Paribbājakakathā"),
        ("D-i", 217, 1, "2. Sāmaññaphalasuttaṃ"),
        ("D-i", 218, 1, "Rājāmaccakathā"),
    ])
    make_headings(src, [h for h in HEADINGS if h[0] == "D-i"])
    with sqlite3.connect(src) as conn:
        conn.execute("CREATE TABLE books (id INT, book_id TEXT)")
        conn.executemany("INSERT INTO books VALUES (?,?)", [(1, "D-i"), (4, "M-i")])
    make_db(tmp_path / "epitaka_kn.db", "translation", translated)
    return str(src)


def test_finished_suttas_get_a_file_each_part_done_ones_are_skipped(tmp_path):
    src = make_sutta_dbs(tmp_path, [  # real Kannada lines; para 218 not translated yet
        ("D-i", 4, 1, "1. ಬ್ರಹ್ಮಜಾಲ ಸುತ್ತ"),
        ("D-i", 5, 1, "ಪರಿವ್ರಾಜಕರ ಕಥೆ"),
        ("D-i", 217, 1, "೨. ಸಾಮಞ್ಞಫಲಸುತ್ತ"),
    ])
    out = tmp_path / "exports" / "kn"

    written, skipped = export_text.export_suttas(src, "kn", str(out))

    assert (written, skipped) == (1, ["dn2: 1 of 2 lines"])
    assert sorted(p.name for p in out.iterdir()) == ["kn_dn1.txt"]
    assert (out / "kn_dn1.txt").read_text(encoding="utf-8") == (
        "1. ಬ್ರಹ್ಮಜಾಲಸುತ್ತಂ\n1. ಬ್ರಹ್ಮಜಾಲ ಸುತ್ತ\n\n"
        "ಪರಿಬ್ಬಾಜಕಕಥಾ\nಪರಿವ್ರಾಜಕರ ಕಥೆ\n\n"
    )


def test_old_txt_files_are_removed_other_files_kept(tmp_path):
    src = make_sutta_dbs(tmp_path, [("D-i", 4, 1, "1. ಬ್ರಹ್ಮಜಾಲ ಸುತ್ತ")])
    out = tmp_path / "exports" / "kn"
    out.mkdir(parents=True)
    (out / "kn_dn1.txt").write_text("old", encoding="utf-8")
    (out / "notes.md").write_text("mine", encoding="utf-8")

    export_text.export_suttas(src, "kn", str(out))

    assert sorted(p.name for p in out.iterdir()) == ["notes.md"]  # dn1 is no longer finished


def test_a_missing_sentence_holds_back_the_sutta_but_bare_punctuation_does_not(tmp_path):
    src = tmp_path / "epitaka.db"
    make_db(src, "pali", [  # real lines: M-i 520.1–2, D-i 424.8
        ("D-i", 4, 1, "1. Brahmajālasuttaṃ"),
        ("D-i", 4, 2, "…"),
        ("D-i", 217, 1, "171.‘‘ Ko ca, bhikkhave, rūpānaṃ assādo?"),
        ("D-i", 217, 2, "Seyyathāpi, bhikkhave, khattiyakaññā vā brāhmaṇakaññā vā"),
    ])
    make_headings(src, [h for h in HEADINGS if h[0] == "D-i"])
    with sqlite3.connect(src) as conn:
        conn.execute("CREATE TABLE books (id INT, book_id TEXT)")
        conn.execute("INSERT INTO books VALUES (1, 'D-i')")
    make_db(tmp_path / "epitaka_kn.db", "translation", [
        ("D-i", 4, 1, "1. ಬ್ರಹ್ಮಜಾಲ ಸುತ್ತ"),
        ("D-i", 217, 1, "171. “ಭಿಕ್ಷುಗಳೇ, ರೂಪಗಳ ಆಸ್ವಾದ ಯಾವುದು?"),
    ])
    out = tmp_path / "exports" / "kn"

    assert export_text.export_suttas(str(src), "kn", str(out)) == (1, ["dn2: 1 of 2 lines"])
    assert sorted(p.name for p in out.iterdir()) == ["kn_dn1.txt"]
