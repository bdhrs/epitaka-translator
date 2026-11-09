import sys

import pytest

sys.argv = sys.argv[:1]
from common import common_utils as cu  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_cache():
    cu._transliterate_segment.cache_clear()
    yield
    cu._transliterate_segment.cache_clear()


def test_markup_survives_and_text_converts():
    out = cu.to_pali_script("<b>bhikkhu</b>", "hi")
    assert out.startswith("<b>") and out.endswith("</b>")
    assert "bhikkhu" not in out
    assert "भिक्खु" in out


def test_number_only_line_stays_roman():
    assert cu.to_pali_script("2933.", "hi") == "2933."


def test_entity_survives():
    assert "&amp;" in cu.to_pali_script("bhikkhu &amp; bhikkhu", "hi")


def test_each_script_target_differs_from_roman():
    for lang in ("hi", "si", "kn", "lo", "km", "bo", "as"):
        assert cu.to_pali_script("bhikkhu", lang) != "bhikkhu", lang


def test_language_without_a_script_is_unchanged():
    assert cu.to_pali_script("bhikkhu", "en") == "bhikkhu"
    assert cu.to_pali_script("", "hi") == ""


def test_round_trip_back_to_roman():
    for word in ("bhikkhu", "dhammacakkappavattana", "saṅgha"):
        assert cu.to_roman_pali(cu.to_pali_script(word, "hi")) == word


def test_roman_input_to_roman_is_unchanged():
    assert cu.to_roman_pali("bhikkhu") == "bhikkhu"


def test_broken_library_falls_back_to_roman_and_warns_once(monkeypatch, capsys):
    def boom(*a):
        raise RuntimeError("no library")
    monkeypatch.setattr(cu, "_aksharamukha_process", boom)
    monkeypatch.setattr(cu, "_warned_conversion_failure", False)

    assert cu.to_pali_script("bhikkhu", "hi") == "bhikkhu"
    assert cu.to_pali_script("dhamma", "hi") == "dhamma"
    assert cu.to_roman_pali("भिक्खु") == "भिक्खु"
    assert capsys.readouterr().out.count("[warn]") == 1
