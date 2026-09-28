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
        "ತತ್ರ ಖೋ\n"
        "\n"
        "\n"
    )
