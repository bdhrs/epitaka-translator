import sys
from pathlib import Path

sys.argv = sys.argv[:1]  # book_translator pre-parses --lang from argv at import time
import book_translator as bt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_commands_use_the_deepseek_name_that_always_points_at_the_latest_flash():
    # "deepseek-flash" has no version number, so it never goes stale; the old name is only routed for now.
    for name in ("justfile", "runner.sh", ".env.example"):
        assert "deepseek:deepseek-v4" not in read(name), name
    assert read("justfile").count("deepseek:deepseek-flash") == 3


def test_fallback_chain_uses_the_same_name():
    assert [m for m in bt.FALLBACK_MODEL_CHAIN if m.startswith("deepseek:")] == ["deepseek:deepseek-flash"]


def test_the_azure_backup_keeps_its_own_deployment_name():
    # User, 2026-10-20: leave Azure alone, it may not have DeepSeek's latest model.
    assert "claude:sonnet+azure:DeepSeek-V4.1-Flash" in read("justfile")
