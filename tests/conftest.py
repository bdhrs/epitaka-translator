import pytest

from common import costs


@pytest.fixture(autouse=True)
def isolated_cost_ledger(monkeypatch, tmp_path):
    """No test may write to the real data/costs.csv."""
    monkeypatch.setattr(costs, "LEDGER", tmp_path / "costs.csv")
    monkeypatch.setattr(costs, "_run_total", 0.0)
    monkeypatch.setattr(costs, "_all_time", None)
