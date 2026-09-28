def test_common_modules_import():
    import common.ai_client
    import common.common_utils
    import common.context_builders

    assert common.ai_client.make_rotator
    assert common.common_utils.lang_db_path
    assert common.context_builders.ParallelTranslationContext
