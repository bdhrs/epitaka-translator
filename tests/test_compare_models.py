import sqlite3
import types
from pathlib import Path

import pytest

import compare_models as cm


def make_data(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    for name in ("epitaka.db", "glossary_kn.db", "epitaka_kn.db", "epitaka_en.db", "dpd-dictionary.db"):
        (data / name).write_text(name)
    return data


def test_scratch_copies_written_files_links_the_rest_and_starts_empty(tmp_path):
    data = make_data(tmp_path)
    scratch = tmp_path / "scratch"

    linked = cm.prepare_scratch(data, scratch, "kn")

    assert not (scratch / "epitaka.db").is_symlink()
    assert not (scratch / "glossary_kn.db").is_symlink()
    assert (scratch / "epitaka_en.db").is_symlink()
    assert (scratch / "dpd-dictionary.db").is_symlink()
    assert not (scratch / "epitaka_kn.db").exists()
    assert sorted(f.name for f in linked) == ["dpd-dictionary.db", "epitaka_en.db"]
    (scratch / "epitaka.db").write_text("changed by the translator")
    assert (data / "epitaka.db").read_text() == "epitaka.db"


def fake_subprocess(calls, busy_models=(), crashing_models=(), bad_export_models=()):
    """Stands in for subprocess.run. Busy: exits 0, saves nothing. Crashing: saves, exits 1."""
    def run(cmd, cwd=None, check=False):
        calls.append(cmd)
        if cmd[2].endswith("book_translator.py"):
            model = cmd[cmd.index("--model") + 1]
            if model in busy_models:
                return types.SimpleNamespace(returncode=0)
            scratch = Path(cmd[cmd.index("--epitaka-db") + 1]).parent
            with sqlite3.connect(scratch / "epitaka_kn.db") as conn:
                conn.execute("CREATE TABLE sentences (translation TEXT)")
                conn.execute("INSERT INTO sentences VALUES ('ok')")
            return types.SimpleNamespace(returncode=1 if model in crashing_models else 0)
        out = Path(cmd[cmd.index("--out") + 1])
        out.write_text("exported")
        model = out.stem
        return types.SimpleNamespace(returncode=1 if model in bad_export_models else 0)
    return run


def test_busy_model_reports_failure_and_good_model_is_exported(monkeypatch, tmp_path):
    data = make_data(tmp_path)
    monkeypatch.setattr(cm, "DATA_DIR", data)
    calls = []
    monkeypatch.setattr(cm.subprocess, "run", fake_subprocess(calls, {"busy-model"}))
    args = types.SimpleNamespace(lang="kn", book="D-i", start=971, end=978)
    out_dir = data / "compare"
    out_dir.mkdir()

    good = cm.run_model("good-model", args, out_dir)
    busy = cm.run_model("busy-model", args, out_dir)

    assert good == out_dir / "good-model.txt" and good.read_text() == "exported"
    assert busy is None
    assert not (out_dir / "busy-model.txt").exists()
    assert not (out_dir / "good-model").exists()
    assert (data / "epitaka.db").read_text() == "epitaka.db"
    translator = [c for c in calls if c[2].endswith("book_translator.py")]
    assert [c[c.index("--model") + 1] for c in translator] == ["good-model", "busy-model"]
    assert all(c[c.index("--epitaka-db") + 1].startswith(str(out_dir)) for c in translator)


def run_models(monkeypatch, tmp_path, models, **fake):
    data = make_data(tmp_path)
    monkeypatch.setattr(cm, "DATA_DIR", data)
    calls = []
    monkeypatch.setattr(cm.subprocess, "run", fake_subprocess(calls, **fake))
    args = types.SimpleNamespace(lang="kn", book="D-i", start=971, end=978)
    out_dir = data / "compare"
    out_dir.mkdir()
    return data, out_dir, {m: cm.run_model(m, args, out_dir) for m in models}


def test_model_name_that_would_point_at_the_data_folder_is_refused(monkeypatch, tmp_path):
    data = make_data(tmp_path)
    monkeypatch.setattr(cm, "DATA_DIR", data)
    monkeypatch.setattr(cm.subprocess, "run", fake_subprocess([]))
    out_dir = data / "compare"
    out_dir.mkdir()
    args = types.SimpleNamespace(lang="kn", book="D-i", start=1, end=2)

    with pytest.raises(SystemExit):
        cm.run_model("..", args, out_dir)

    assert (data / "epitaka.db").exists() and (data / "epitaka_kn.db").exists()


def test_old_result_does_not_survive_a_failed_rerun(monkeypatch, tmp_path):
    data = make_data(tmp_path)
    monkeypatch.setattr(cm, "DATA_DIR", data)
    out_dir = data / "compare"
    out_dir.mkdir()
    (out_dir / "busy-model.txt").write_text("from an earlier run")
    monkeypatch.setattr(cm.subprocess, "run", fake_subprocess([], busy_models={"busy-model"}))
    args = types.SimpleNamespace(lang="kn", book="D-i", start=1, end=2)

    assert cm.run_model("busy-model", args, out_dir) is None
    assert not (out_dir / "busy-model.txt").exists()


def test_translator_error_exit_is_a_failure_even_if_lines_were_saved(monkeypatch, tmp_path):
    data, out_dir, results = run_models(monkeypatch, tmp_path, ["crash-model"], crashing_models={"crash-model"})

    assert results["crash-model"] is None
    assert not (out_dir / "crash-model.txt").exists()
    assert not (out_dir / "crash-model").exists()


def test_failed_export_fails_that_model_only_and_cleans_up(monkeypatch, tmp_path):
    data, out_dir, results = run_models(
        monkeypatch, tmp_path, ["bad-export", "good-model"], bad_export_models={"bad-export"},
    )

    assert results["bad-export"] is None
    assert results["good-model"] == out_dir / "good-model.txt"
    assert not (out_dir / "bad-export.txt").exists()
    assert not (out_dir / "bad-export").exists()
