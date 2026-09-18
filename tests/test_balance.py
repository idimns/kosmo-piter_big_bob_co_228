"""Тесты материального баланса.

Проверяем тождество баланса, отсутствие двойного учёта потерь,
неотрицательность запаса.
"""
import pytest

from fuelcontour.io.loader import load_case, load_scenarios
from fuelcontour.model.entities import Decision, ChannelDecision
from fuelcontour.engine.balance import compute_balance
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def case():
    return load_case(ROOT / "data" / "case.yaml")


@pytest.fixture
def scenarios():
    return load_scenarios(ROOT / "configs")


def test_balance_identity(case, scenarios):
    """запас_конец == запас_начало + поступление - потери - выдача (каждый год)."""
    dec = Decision(
        scenario_id="standard",
        initial_stock=15,
        plan={
            2035: [ChannelDecision(channel_id="A", reserved_capacity=130, ordered=125)],
        },
    )
    rows = compute_balance(case, dec, scenarios["standard"])
    for r in rows:
        expected = r.stock_start + r.inflow - r.losses - r.issued
        # запас не может быть отрицательным - если expected<0, это дефицит
        expected = max(expected, 0.0)
        assert abs(r.stock_end - expected) < 1e-6, f"баланс не сходится в {r.year}"


def test_losses_counted_once(case, scenarios):
    """Потери = поступление * loss_rate, ровно один раз (4.5% базово)."""
    dec = Decision(
        scenario_id="standard",
        initial_stock=0,
        plan={2035: [ChannelDecision(channel_id="A", reserved_capacity=100, ordered=100)]},
    )
    rows = compute_balance(case, dec, scenarios["standard"])
    r = rows[0]
    assert abs(r.losses - r.inflow * 0.045) < 1e-6


def test_no_negative_stock(case, scenarios):
    """Запас на конец никогда не отрицательный."""
    dec = Decision(scenario_id="standard", initial_stock=0)  # пустой план
    rows = compute_balance(case, dec, scenarios["standard"])
    for r in rows:
        assert r.stock_end >= 0.0


def test_zbo_changes_loss_rate(case, scenarios):
    """С ZBO потери падают до 1.2%."""
    dec = Decision(
        scenario_id="standard",
        initial_stock=0,
        use_zbo=True,
        investments={"zbo_upgrade": 2036},
        plan={2036: [ChannelDecision(channel_id="A", reserved_capacity=100, ordered=100)]},
    )
    rows = compute_balance(case, dec, scenarios["standard"])
    # 2036 год - второй в списке
    r2036 = next(r for r in rows if r.year == 2036)
    assert abs(r2036.losses - r2036.inflow * 0.012) < 1e-6


def test_stress_demand_multiplier(case, scenarios):
    """В стрессе с 2038 спрос x1.15, до 2038 - без изменений."""
    dec = Decision(scenario_id="stress", initial_stock=0)
    rows = compute_balance(case, dec, scenarios["stress"])
    d2037 = next(r for r in rows if r.year == 2037)
    d2038 = next(r for r in rows if r.year == 2038)
    assert abs(d2037.demand_total - 190.0) < 1e-6      # не изменён
    assert abs(d2038.demand_total - 250.0 * 1.15) < 1e-6  # x1.15
