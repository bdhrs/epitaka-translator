from common.context_builders import ParallelTranslationContext


def test_an_unreadable_parallel_db_is_logged_and_skipped(tmp_path):
    warnings = []
    context = ParallelTranslationContext({}, "B", 1, 5, log_warn=warnings.append)
    unreadable = tmp_path / "no_such_folder" / "epitaka_hi.db"  # SQLite cannot create a file in a missing folder

    assert context._fetch_translations(unreadable, 5) == []
    assert len(warnings) == 1
    assert "epitaka_hi.db" in warnings[0]
