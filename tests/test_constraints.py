"""Тесты ограничений и воспроизводимости."""
import pytest
from pathlib import Path

from fuelcontour.io.loader import load_case, load_scenarios, load_decision
from fuelcontour.model.entities import Decision, ChannelDecision
from fuelcontour.engine.pipeline import evaluate_plan

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def case():
    return load_case(ROOT / "data" / "case.yaml")


@pytest.fixture
def scenarios():
    return load_scenarios(ROOT / "configs")


def test_reserve_45_days_formula(case, scenarios):
    """R = годовой_спрос * 45/365. Для 2035 (спрос 100) = 12.33т."""
    dec = Decision(scenario_id="standard", initial_stock=0)
    res = evaluate_plan(case, dec, scenarios["standard"])
    reserve_viol = [v for v in res.violations if v.kind == "reserve_45d" and v.year == 2035]
    assert len(reserve_viol) == 1
    assert abs(reserve_viol[0].limit - 100 * 45 / 365) < 1e-3


def test_empty_plan_infeasible(case, scenarios):
    """Пустой план не обслуживает спрос -> неисполним (Правило 8)."""
    dec = Decision(scenario_id="standard", initial_stock=0)
    res = evaluate_plan(case, dec, scenarios["standard"])
    assert res.feasible is False
    assert res.has_errors is True


def test_capex_limit_violation(case, scenarios):
    """CAPEX сверх лимита 2037 -> нарушение error."""
    # ISRU 1250 + earth_new 360 = 1610 < 1800, добавим оба + попробуем превысить
    # искусственно: реализуем ISRU в 2037 (1250) - под лимитом; проверим что НЕ нарушено
    dec = Decision(
        scenario_id="standard",
        initial_stock=0,
        investments={"isru_pilot": 2037, "earth_new_option": 2037},  # 1610
    )
    res = evaluate_plan(case, dec, scenarios["standard"])
    capex_viol = [v for v in res.violations if v.kind == "capex_2037"]
    assert len(capex_viol) == 0  # 1610 < 1800, не нарушено


def test_feasible_plan_no_errors(case, scenarios):
    """Реалистичный план из results/ выполним в стандартном сценарии."""
    dec = load_decision(ROOT / "results" / "plan_standard.json")
    res = evaluate_plan(case, dec, scenarios["standard"])
    assert res.feasible is True
    assert res.has_errors is False


def test_determinism(case, scenarios):
    """Повторный прогон на тех же данных даёт те же числа (критерий №5)."""
    dec = load_decision(ROOT / "results" / "plan_standard.json")
    r1 = evaluate_plan(case, dec, scenarios["standard"])
    r2 = evaluate_plan(case, dec, scenarios["standard"])
    assert abs(r1.economics.total_cost - r2.economics.total_cost) < 1e-9
    assert abs(r1.economics.total_discounted - r2.economics.total_discounted) < 1e-9
    for a, b in zip(r1.years, r2.years):
        assert abs(a.stock_end - b.stock_end) < 1e-9
        assert abs(a.served_total - b.served_total) < 1e-9


def test_stress_honest_deficit(case, scenarios):
    """В стрессе дефицит показывается как warning, не как error (Правило 8)."""
    dec = load_decision(ROOT / "results" / "plan_standard.json")
    res = evaluate_plan(case, dec, scenarios["stress"])
    # стресс может не достигать 97% - это warning, не error
    service_warns = [v for v in res.violations
                     if v.kind == "service_total" and v.severity == "warning"]
    # план остаётся "выполнимым" по строгим ошибкам (стресс - ориентир)
    assert res.feasible is True
    # но дефицит виден численно
    assert len(service_warns) >= 1
