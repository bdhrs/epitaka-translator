import inspect
import sys

import pytest

sys.argv = sys.argv[:1]  # book_translator pre-parses --lang from argv at import time
import book_translator as bt  # noqa: E402


@pytest.mark.parametrize(
    "lang, expected",
    [
        ("kn", {"epitaka_en.db", "epitaka_hi.db", "epitaka_si.db"}),
        ("mr", {"epitaka_en.db", "epitaka_hi.db", "epitaka_si.db"}),
        ("hi", {"epitaka_en.db", "epitaka_th.db", "epitaka_si.db"}),
        ("vi", {"epitaka_en.db", "epitaka_th.db", "epitaka_si.db"}),
        ("th", {"epitaka_en.db", "epitaka_th.db", "epitaka_si.db"}),
    ],
)
def test_parallel_ref_dbs(lang, expected):
    assert bt.parallel_ref_dbs(lang) == expected


def test_process_book_uses_parallel_ref_dbs():
    src = inspect.getsource(bt.process_book)
    assert "only_langs=parallel_ref_dbs(args.lang)" in src


def test_kannada_prompt_names_hindi_not_thai():
    prompt = bt._build_system_prompt("kn")
    assert "existing English/Hindi/Sinhala human" in prompt
    assert "Hindi (Devanagari), Sinhala, and Myanmar appear only as" in prompt
    assert "Devanagari does\nnot appear" not in prompt
    assert "English/Thai/Sinhala" not in prompt


def test_vietnamese_prompt_keeps_thai():
    prompt = bt._build_system_prompt("vi")
    assert "existing English/Thai/Sinhala human" in prompt
    assert "Devanagari does\nnot appear" in prompt


def test_kannada_prompt_forbids_roman():
    prompt = bt._build_system_prompt("kn")
    assert "Never use Roman (Latin) letters anywhere in Kannada (ಕನ್ನಡ) output." in prompt
    assert "Never use Roman" not in bt._build_system_prompt("vi")


@pytest.mark.parametrize("text", ["ನಿಬ್ಬಾಣ (nibbāna)", "Buddha ಹೇಳಿದರು", "ಸತಿ ṃ"])
def test_roman_letters_flagged_for_kannada(text):
    assert bt.roman_bleed("kn", text)
    flagged = bt.check_translations_for_script_bleed("kn", [{"translation": text}])
    assert len(flagged) == 1 and flagged[0]["translation"] == ""


def test_kannada_with_tags_and_digits_passes():
    text = "<b>ಸತಿ</b> ಎಂದರೆ <i>ಸತಿ</i> ೧೦೫. 105 &nbsp;"
    assert bt.roman_bleed("kn", text) == ""
    assert bt.check_translations_for_script_bleed("kn", [{"translation": text}]) == []


def test_roman_glossary_term_flagged_for_kannada():
    clean, flagged = bt.check_glossary_terms_for_script_bleed(
        "kn", [{"pali": "sati", "translation": "sati"}, {"pali": "sati", "translation": "ಸ್ಮೃತಿ"}]
    )
    assert [t["translation"] for t in flagged] == ["sati"]
    assert [t["translation"] for t in clean] == ["ಸ್ಮೃತಿ"]


def test_vietnamese_roman_is_fine():
    assert bt.roman_bleed("vi", "chánh niệm") == ""


def test_numeric_entities_are_not_roman():
    assert bt.roman_bleed("kn", "ಸತಿ&#x2014;ಪಟ್ಠಾನ &#8212; &amp;") == ""


def test_pinned_model_without_keys_stops_before_work(monkeypatch, capsys):
    for k in list(bt.os.environ):
        if "_KEY_" in k:
            monkeypatch.delenv(k)
    monkeypatch.setenv("GEMINI_KEY_1", "g1")
    monkeypatch.setattr(sys, "argv", ["bt", "--lang", "kn", "--books", "M-i", "--dry-run",
                                      "--model", "deepseek:deepseek-v4-flash"])
    assert bt.main() == 1
    out = capsys.readouterr().out
    assert "set DEEPSEEK_KEY_1 in .env" in out
    assert "All API keys exhausted" not in out
