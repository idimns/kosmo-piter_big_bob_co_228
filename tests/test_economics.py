"""Тесты экономики.

Главный фокус - формула take-or-pay и анти-двойной-учёт.
Есть независимый ручной (golden) пример.
"""
import pytest
from pathlib import Path

from fuelcontour.io.loader import load_case, load_scenarios
from fuelcontour.model.entities import Decision, ChannelDecision
from fuelcontour.engine.economics import (
    variable_payment, reservation_payment, take_or_pay_gap, compute_economics,
)
from fuelcontour.engine.balance import compute_balance

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def case():
    return load_case(ROOT / "data" / "case.yaml")


@pytest.fixture
def scenarios():
    return load_scenarios(ROOT / "configs")


def test_variable_payment_uses_max_not_sum():
    """переменный платёж = цена * max(отбор, ToP*резерв). НЕ сумма!"""
    # отбор ниже ToP-минимума -> платим за минимум
    p = variable_payment(price=6.2, drawn=50, take_or_pay=0.70, reserved_capacity=190)
    top_min = 0.70 * 190  # = 133
    assert abs(p - 6.2 * 133) < 1e-6

    # отбор выше ToP-минимума -> платим за отбор
    p2 = variable_payment(price=6.2, drawn=180, take_or_pay=0.70, reserved_capacity=190)
    assert abs(p2 - 6.2 * 180) < 1e-6


def test_take_or_pay_not_double_counted():
    """ToP-штраф уже внутри variable_payment, не прибавляется отдельно."""
    drawn, top, res, price = 50, 0.70, 190, 6.2
    var = variable_payment(price, drawn, top, res)
    gap = take_or_pay_gap(price, drawn, top, res)
    # var уже = price*top_min; gap - это лишь та часть, что сверх отбора
    # проверяем что gap = price*(top_min - drawn), а var не включает drawn дважды
    assert abs(gap - price * (0.70 * 190 - 50)) < 1e-6
    assert abs(var - price * 0.70 * 190) < 1e-6


def test_reservation_full_year():
    """резерв за полный год = тариф * мощность."""
    r = reservation_payment(rate=0.45, reserved_capacity=190, year_fraction=1.0)
    assert abs(r - 0.45 * 190) < 1e-6


def test_reservation_partial_year():
    """резерв за часть года пропорционален."""
    r = reservation_payment(rate=0.45, reserved_capacity=190, year_fraction=0.5)
    assert abs(r - 0.45 * 190 * 0.5) < 1e-6


def test_golden_single_year(case, scenarios):
    """Golden: один год, канал A, известный ручной расчёт.

    Ручной расчёт для 2035:
      начальный запас = 0, заказ A = 100, мощность A = 190 (доступна)
      поставка = 100
      потери = 100 * 0.045 = 4.5
      доступно к выдаче = 0 + 100 - 4.5 = 95.5
      спрос 2035 = 100 -> выдача = min(100, 95.5) = 95.5
      запас конец = 95.5 - 95.5 = 0

    Экономика 2035:
      переменный = 6.2 * max(100, 0.70*130) = 6.2 * max(100, 91) = 6.2*100 = 620
      резерв = 0.45 * 130 = 58.5
      хранение = 0.72 * (0 + 0)/2 = 0
      итого 2035 = 620 + 58.5 + 0 = 678.5
    """
    dec = Decision(
        scenario_id="standard",
        initial_stock=0,
        plan={2035: [ChannelDecision(channel_id="A", reserved_capacity=130, ordered=100)]},
    )
    rows = compute_balance(case, dec, scenarios["standard"])
    econ = compute_economics(case, dec, rows, scenarios["standard"])

    r = rows[0]
    assert abs(r.inflow - 100) < 1e-6
    assert abs(r.losses - 4.5) < 1e-6
    assert abs(r.issued - 95.5) < 1e-6
    assert abs(r.stock_end - 0.0) < 1e-6

    # экономика
    assert abs(econ.var_cost_by_year[2035] - 620.0) < 1e-6
    assert abs(econ.reservation_by_year[2035] - 58.5) < 1e-6
    assert abs(econ.total_by_year[2035] - 678.5) < 1e-6


def test_capex_schedule(case, scenarios):
    """CAPEX начисляется в год реализации инвестиции."""
    dec = Decision(
        scenario_id="standard",
        initial_stock=0,
        investments={"earth_new_option": 2037},
    )
    rows = compute_balance(case, dec, scenarios["standard"])
    econ = compute_economics(case, dec, rows, scenarios["standard"])
    assert abs(econ.capex_by_year.get(2037, 0) - 360.0) < 1e-6
    assert abs(econ.capex_cumulative_2037 - 360.0) < 1e-6
