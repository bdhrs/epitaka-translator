import sqlite3

import pytest

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
        "105. ಏವಂ ಮೇ ಸುತಂ ಭಗವಾ\n\n"
        "ನಾನು ಹೀಗೆ ಕೇಳಿದೆನು\n\n\n"
    )  # para 282 has no translation yet, so it is left out


def make_remarks(path, rows):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE translation_remarks (id INTEGER PRIMARY KEY, book_id TEXT, para_id INT, "
                     "line_id INT, translation TEXT, conflict TEXT, note TEXT)")
        conn.executemany("INSERT INTO translation_remarks (book_id, para_id, line_id, translation, conflict, note) "
                         "VALUES (?,?,?,?,?,?)", rows)


def remark_fixture(tmp_path):
    src = tmp_path / "epitaka.db"
    make_db(src, "pali", [("M-i", 281, 1, "Evaṃ me sutaṃ"), ("M-i", 282, 1, "Tatra kho")])
    lang_db = tmp_path / "epitaka_kn.db"
    make_db(lang_db, "translation", [("M-i", 281, 1, "ನಾನು ಹೀಗೆ ಕೇಳಿದೆನು"), ("M-i", 282, 1, "ಅಲ್ಲಿ")])
    make_remarks(lang_db, [
        ("M-i", 281, 1, "ಹೀಗೆ ಕೇಳಿದ್ದೇನೆ", "'sutaṃ' ಅನುವಾದಿಸಿಲ್ಲ", "wrong"),
        ("M-i", 282, 1, "ಹಳೆಯದು", "translator's own explanation", "ಅಟ್ಠಕಥೆ ಅನುಸರಿಸಿದೆ"),
    ])
    return src


def test_review_remarks_follow_their_paragraph_exactly_as_written(tmp_path):
    text = export_text.export_text(str(remark_fixture(tmp_path)), "kn", "M-i", 280, 410)

    assert text == (
        "ಏವಂ ಮೇ ಸುತಂ\n\n"
        "ನಾನು ಹೀಗೆ ಕೇಳಿದೆನು\n\n"
        "ಪರಿಶೀಲನಾ ಟಿಪ್ಪಣಿಗಳು:\n"
        "  ಲೈನ್ 1 [ತಪ್ಪು]: 'sutaṃ' ಅನುವಾದಿಸಿಲ್ಲ\n"
        "    ಸೂಚಿತ ತಿದ್ದುಪಡಿ: ಹೀಗೆ ಕೇಳಿದ್ದೇನೆ\n"
        "\n\n"
        "ತತ್ರ ಖೋ\n\n"
        "ಅಲ್ಲಿ\n\n\n"
    )  # the translator's own remark (note is not a severity) stays out


def test_remarks_can_be_left_out(tmp_path):
    text = export_text.export_text(str(remark_fixture(tmp_path)), "kn", "M-i", 280, 410, remarks=False)

    assert "ಪರಿಶೀಲನಾ" not in text


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
        conn.execute("CREATE TABLE books (id INT, book_id TEXT, nikaya TEXT, sub_nikaya TEXT)")
        conn.executemany("INSERT INTO books VALUES (?,?,?,?)", [
            (1, "D-i", "Sutta Piṭaka", "Dīgha Nikāya"), (4, "M-i", "Sutta Piṭaka", "Majjhima Nikāya")])
    make_db(tmp_path / "epitaka_kn.db", "translation", translated)
    return str(src)


def test_finished_suttas_go_in_their_book_file_part_done_ones_are_skipped(tmp_path):
    src = make_sutta_dbs(tmp_path, [  # real Kannada lines; para 218 not translated yet
        ("D-i", 4, 1, "1. ಬ್ರಹ್ಮಜಾಲ ಸುತ್ತ"),
        ("D-i", 5, 1, "ಪರಿವ್ರಾಜಕರ ಕಥೆ"),
        ("D-i", 217, 1, "೨. ಸಾಮಞ್ಞಫಲಸುತ್ತ"),
    ])
    out = tmp_path / "exports" / "kn"
    root = tmp_path / "exports"

    written, skipped = export_text.export_suttas(src, "kn", str(root))

    assert (written, skipped) == (1, ["dn2: 1 of 2 lines"])
    assert [p.name for p in out.glob("*/*.txt")] == ["01_D-i.txt"]
    assert (out / "01_Digha_Nikaya" / "01_D-i.txt").read_text(encoding="utf-8") == (
        "1. ಬ್ರಹ್ಮಜಾಲಸುತ್ತಂ\n\n1. ಬ್ರಹ್ಮಜಾಲ ಸುತ್ತ\n\n\n"
        "ಪರಿಬ್ಬಾಜಕಕಥಾ\n\nಪರಿವ್ರಾಜಕರ ಕಥೆ\n\n\n"
    )


def test_old_txt_files_are_removed_other_files_kept(tmp_path):
    src = make_sutta_dbs(tmp_path, [("D-i", 4, 1, "1. ಬ್ರಹ್ಮಜಾಲ ಸುತ್ತ")])
    out = tmp_path / "exports" / "kn"
    root = tmp_path / "exports"
    (out / "09_Old_Folder").mkdir(parents=True)
    (out / "kn_dn1.txt").write_text("old", encoding="utf-8")
    (out / "09_Old_Folder" / "01_D-i.txt").write_text("old", encoding="utf-8")
    (out / "notes.md").write_text("mine", encoding="utf-8")

    export_text.export_suttas(src, "kn", str(root))

    assert sorted(p.name for p in out.iterdir()) == [export_text.README_NAME, "notes.md"]  # dn1 is no longer finished: no old .txt, no empty old folder


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
        conn.execute("CREATE TABLE books (id INT, book_id TEXT, nikaya TEXT, sub_nikaya TEXT)")
        conn.execute("INSERT INTO books VALUES (1, 'D-i', 'Sutta Piṭaka', 'Dīgha Nikāya')")
    make_db(tmp_path / "epitaka_kn.db", "translation", [
        ("D-i", 4, 1, "1. ಬ್ರಹ್ಮಜಾಲ ಸುತ್ತ"),
        ("D-i", 217, 1, "171. “ಭಿಕ್ಷುಗಳೇ, ರೂಪಗಳ ಆಸ್ವಾದ ಯಾವುದು?"),
    ])
    out = tmp_path / "exports" / "kn"
    root = tmp_path / "exports"

    assert export_text.export_suttas(str(src), "kn", str(root)) == (1, ["dn2: 1 of 2 lines"])
    assert [p.name for p in out.glob("*/*.txt")] == ["01_D-i.txt"]


def test_files_and_folders_are_numbered_in_canon_order(tmp_path):
    src = tmp_path / "epitaka.db"
    make_db(src, "pali", [
        ("D-i", 4, 1, "1. Brahmajālasuttaṃ"), ("D-i", 217, 1, "2. Sāmaññaphalasuttaṃ"),
        ("Khp", 4, 1, "1. Saraṇattayaṃ"),
    ])
    make_headings(src, [("D-i", 4, 2, "x", "dn1"), ("D-i", 217, 2, "y", "dn2"), ("Khp", 4, 2, "z", "kp1")])
    with sqlite3.connect(src) as conn:
        conn.execute("CREATE TABLE books (id INT, book_id TEXT, nikaya TEXT, sub_nikaya TEXT)")
        conn.executemany("INSERT INTO books VALUES (?,?,?,?)", [
            (1, "D-i", "Sutta Piṭaka", "Dīgha Nikāya"), (23, "Khp", "Sutta Piṭaka", "Khuddaka Nikāya"),
            (45, "Vin-i", "Vinaya Piṭaka", "")])
    make_db(tmp_path / "epitaka_kn.db", "translation", [
        ("D-i", 4, 1, "ಒಂದು"), ("D-i", 217, 1, "ಎರಡು"), ("Khp", 4, 1, "ಮೂರು")])
    out = tmp_path / "exports" / "kn"
    root = tmp_path / "exports"

    export_text.export_suttas(str(src), "kn", str(root))

    assert sorted(str(p.relative_to(out)) for p in out.glob("*/*.txt")) == [
        "01_Digha_Nikaya/01_D-i.txt", "02_Khuddaka_Nikaya/01_Khp.txt"]
    text = (out / "01_Digha_Nikaya" / "01_D-i.txt").read_text(encoding="utf-8")
    assert text.index("ಒಂದು") < text.index("ಎರಡು")  # both suttas, in order, in the one book file


def test_a_book_too_big_for_one_doc_is_split_between_suttas(tmp_path, monkeypatch):
    src = make_sutta_dbs(tmp_path, [("D-i", 4, 1, "ಒಂದು"), ("D-i", 5, 1, "ಒಂದು ಕಥೆ"),
                                    ("D-i", 217, 1, "ಎರಡು"), ("D-i", 218, 1, "ಎರಡು ಕಥೆ")])
    monkeypatch.setattr(export_text, "MAX_FILE_CHARS", 60)
    root = tmp_path / "exports"

    export_text.export_suttas(src, "kn", str(root))

    files = sorted((root / "kn" / "01_Digha_Nikaya").iterdir())
    assert [f.name for f in files] == ["01_D-i_1.txt", "01_D-i_2.txt"]
    assert "ಒಂದು" in files[0].read_text(encoding="utf-8") and "ಎರಡು" not in files[0].read_text(encoding="utf-8")
    assert "ಎರಡು" in files[1].read_text(encoding="utf-8")


def test_a_transliterator_that_returns_nothing_is_an_error(monkeypatch):
    import aksharamukha.transliterate as transliterate

    monkeypatch.setattr(transliterate, "process", lambda *_: None)

    with pytest.raises(ValueError, match="returned nothing"):
        export_text._to_script("evaṃ", "Kannada")


def nested_book(tmp_path):
    # Real shape of Vin-v: one level-1 "sutta" holds the whole book, level-2 suttas sit inside it.
    src = tmp_path / "epitaka.db"
    paras = [(4, "Parivārapāḷi", "ಪರಿವಾರ"), (5, "Pāli five", "ಐದು"), (10, "Samuṭṭhāna", "ಸಮುಟ್ಠಾನ"),
             (11, "Pāli eleven", "ಹನ್ನೊಂದು"), (20, "Antarapeyyālaṃ", "ಅಂತರ"), (21, "Pāli twenty-one", "ಇಪ್ಪತ್ತೊಂದು")]
    make_db(src, "pali", [("Vin-v", p, 1, pali) for p, pali, _ in paras])
    make_headings(src, [("Vin-v", 4, 1, "x", "pvr-name"), ("Vin-v", 10, 2, "y", "pvr3"), ("Vin-v", 20, 2, "z", "pvr4")])
    with sqlite3.connect(src) as conn:
        conn.execute("CREATE TABLE books (id INT, book_id TEXT, nikaya TEXT, sub_nikaya TEXT)")
        conn.execute("INSERT INTO books VALUES (45, 'Vin-v', 'Vinaya Piṭaka', '')")
    make_db(tmp_path / "epitaka_kn.db", "translation", [("Vin-v", p, 1, kn) for p, _, kn in paras])
    return str(src)


def test_a_sutta_inside_another_is_not_written_twice(tmp_path):
    src = nested_book(tmp_path)

    export_text.export_suttas(src, "kn", str(tmp_path / "exports"))

    (book_file,) = (tmp_path / "exports" / "kn" / "01_Vinaya_Piṭaka".replace("ṭ", "t")).iterdir()
    assert book_file.read_text(encoding="utf-8").count("ಹನ್ನೊಂದು") == 1


def test_a_sutta_too_big_for_one_doc_is_cut_before_a_heading_inside_it(tmp_path, monkeypatch):
    src = nested_book(tmp_path)
    monkeypatch.setattr(export_text, "MAX_FILE_CHARS", 50)

    export_text.export_suttas(src, "kn", str(tmp_path / "exports"))

    files = sorted((tmp_path / "exports" / "kn" / "01_Vinaya_Pitaka").iterdir())
    texts = [f.read_text(encoding="utf-8") for f in files]
    assert len(files) == 3
    assert texts[0].startswith("ಪರಿವಾರ") and texts[1].startswith("ಸಮುಟ್ಠಾನ") and texts[2].startswith("ಅಂತರ")


def test_every_language_folder_gets_the_readme_with_its_language_name(tmp_path):
    src = make_sutta_dbs(tmp_path, [("D-i", 4, 1, "1. ಬ್ರಹ್ಮಜಾಲ ಸುತ್ತ"), ("D-i", 5, 1, "ಕಥೆ")])

    export_text.export_suttas(src, "kn", str(tmp_path / "exports"))

    text = (tmp_path / "exports" / "kn" / "!!! README FIRST.txt").read_text(encoding="utf-8")
    assert "in the Kannada script" in text and "(ಕನ್ನಡ)" not in text and "{language}" not in text


def test_a_file_over_the_google_doc_limit_prints_a_warning(tmp_path, monkeypatch, capsys):
    src = nested_book(tmp_path)
    monkeypatch.setattr(export_text, "GOOGLE_DOC_LIMIT", 50)

    export_text.export_suttas(src, "kn", str(tmp_path / "exports"))

    assert "WARNING: 01_Vin-v.txt has" in capsys.readouterr().out


def test_export_uses_the_shared_script_map():
    assert export_text.PALI_SCRIPTS is export_text.cu.PALI_SCRIPT_BY_LANG
    assert export_text.PALI_SCRIPTS["kn"] == "Kannada"
