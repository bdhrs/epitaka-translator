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


def test_export_all_is_canon_order_with_headings(tmp_path):
    src = tmp_path / "epitaka.db"
    make_db(src, "pali", [
        ("M-i", 1, 1, "Evaṃ me sutaṃ"),
        ("D-i", 1, 1, "Tatra kho"),
        ("A-i", 1, 1, "Bhagavā"),
        ("S-i", 1, 1, "Sāvatthiyaṃ"),
    ])
    with sqlite3.connect(src) as conn:
        conn.execute("CREATE TABLE books (id INT, book_id TEXT, book_name TEXT)")
        conn.executemany("INSERT INTO books VALUES (?,?,?)",
                         [(1, "D-i", "DN1-Sīlakkhandhavaggapāḷi"), (2, "M-i", "MN1-Mūlapaṇṇāsapāḷi"),
                          (3, "S-i", "SN1-Sagāthāvaggo"), (4, "A-i", "AN1-Ekakanipātapāḷi")])
    make_db(tmp_path / "epitaka_kn.db", "translation", [
        ("M-i", 1, 1, "ನಾನು ಹೀಗೆ ಕೇಳಿದೆನು"),
        ("D-i", 1, 1, "ಅಲ್ಲಿ"),
        ("A-i", 1, 1, "ಭಗವಂತ"),
    ])

    assert export_text.export_all(str(src), "kn") == (
        "ಸೀಲಕ್ಖಂಧವಗ್ಗಪಾಳಿ\n\nತತ್ರ ಖೋ\nಅಲ್ಲಿ\n\n"
        "ಮೂಲಪಣ್ಣಾಸಪಾಳಿ\n\nಏವಂ ಮೇ ಸುತಂ\nನಾನು ಹೀಗೆ ಕೇಳಿದೆನು\n\n"
        "ಏಕಕನಿಪಾತಪಾಳಿ\n\nಭಗವಾ\nಭಗವಂತ\n\n"
    )  # canon order (D, M, A), not name order; untranslated S-i left out
