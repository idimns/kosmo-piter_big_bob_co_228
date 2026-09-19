"""Тесты оптимизатора, чувствительности и Монте-Карло."""
import pytest
from pathlib import Path

from fuelcontour.io.loader import load_case, load_scenarios, load_decision
from fuelcontour.engine.optimizer import optimize_plan, optimize_and_verify
from fuelcontour.engine.sensitivity import sweep_channel_price, tornado
from fuelcontour.engine.montecarlo import run_montecarlo
from fuelcontour.engine.pipeline import evaluate_plan

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def case():
    return load_case(ROOT / "data" / "case.yaml")


@pytest.fixture
def scenarios():
    return load_scenarios(ROOT / "configs")


@pytest.fixture
def plan():
    return load_decision(ROOT / "results" / "plan_recommended.json")


# --- оптимизатор ---

def test_optimizer_standard_verified_feasible(case, scenarios):
    """Оптимизатор выдаёт план, который движок считает исполнимым."""
    res = optimize_and_verify(case, scenarios["standard"], time_limit=20)
    assert res["feasible"] is True
    # проверяем что engine согласен
    check = evaluate_plan(case, res["decision"], scenarios["standard"])
    assert check.feasible is True
    assert not check.has_errors


def test_optimizer_stress_feasible(case, scenarios):
    res = optimize_and_verify(case, scenarios["stress"], time_limit=20)
    assert res["feasible"] is True
    check = evaluate_plan(case, res["decision"], scenarios["stress"])
    # в стрессе критический спрос должен держаться
    for r in check.years:
        assert r.service_critical_ratio >= 0.99 - 1e-6


def test_optimizer_lower_bound_below_engine(case, scenarios):
    """MILP-оценка снизу не выше проверенной движком стоимости (иначе это не
    оценка снизу, а ошибка модели)."""
    res = optimize_and_verify(case, scenarios["standard"], time_limit=20)
    assert res["lower_bound"] <= res["engine_discounted"] + 1e-6


def test_optimizer_respects_capex_cap(case, scenarios):
    res = optimize_and_verify(case, scenarios["standard"], time_limit=20)
    check = evaluate_plan(case, res["decision"], scenarios["standard"])
    assert check.economics.capex_cumulative_2037 <= case.constraints.capex_cap_2037 + 1e-6


# --- чувствительность ---

def test_sensitivity_price_monotonic(case, scenarios, plan):
    """Рост цены канала -> неубывающие суммарные расходы."""
    r = sweep_channel_price(case, plan, scenarios["standard"], "A", [0.8, 1.0, 1.2, 1.4])
    costs = [p.total_cost for p in r.points]
    assert costs == sorted(costs)  # монотонно растут


def test_tornado_identifies_price_a(case, scenarios, plan):
    """Торнадо: цена A - крупнейший фактор (основной канал)."""
    t = tornado(case, plan, scenarios["standard"], delta=0.2)
    factors = list(t["factors"].keys())
    assert factors[0] == "price_A"  # первый по влиянию


# --- монте-карло ---

def test_montecarlo_deterministic_with_seed(case, scenarios, plan):
    """Один seed -> идентичный результат (воспроизводимость)."""
    a = run_montecarlo(case, plan, scenarios["stress"], trials=500, seed=7)
    b = run_montecarlo(case, plan, scenarios["stress"], trials=500, seed=7)
    assert a.mean_shortfall == b.mean_shortfall
    assert a.p95_shortfall == b.p95_shortfall
    assert a.prob_meets_critical == b.prob_meets_critical


def test_montecarlo_different_seed_differs(case, scenarios, plan):
    """Разные seed -> разные прогоны (действительно случайно)."""
    a = run_montecarlo(case, plan, scenarios["stress"], trials=500, seed=1)
    b = run_montecarlo(case, plan, scenarios["stress"], trials=500, seed=2)
    # хотя бы одна метрика отличается
    assert a.mean_shortfall != b.mean_shortfall or a.max_shortfall != b.max_shortfall


def test_montecarlo_probabilities_in_range(case, scenarios, plan):
    mc = run_montecarlo(case, plan, scenarios["standard"], trials=500, seed=42)
    assert 0.0 <= mc.prob_meets_total <= 1.0
    assert 0.0 <= mc.prob_meets_critical <= 1.0
    assert mc.p95_shortfall >= mc.p50_shortfall  # перцентили упорядочены
    assert mc.max_shortfall >= mc.p95_shortfall
