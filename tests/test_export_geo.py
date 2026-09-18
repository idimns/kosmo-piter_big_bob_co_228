"""Тесты выгрузки и геополитического модуля."""
import pytest
from pathlib import Path

from fuelcontour.io.loader import load_case, load_scenarios, load_decision
from fuelcontour.engine.pipeline import evaluate_plan
from fuelcontour.engine.geopolitical import GeoEvent, run_geopolitical
from fuelcontour.io.export import export_xlsx, result_to_csv_string, _year_rows_df

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def case():
    return load_case(ROOT / "data" / "case.yaml")


@pytest.fixture
def scenarios():
    return load_scenarios(ROOT / "configs")


@pytest.fixture
def plan():
    return load_decision(ROOT / "results" / "plan_standard.json")


def test_export_xlsx_written(case, scenarios, plan, tmp_path):
    res = evaluate_plan(case, plan, scenarios["standard"])
    fp = export_xlsx(res, tmp_path / "out.xlsx")
    assert fp.exists()
    assert fp.stat().st_size > 0


def test_export_numbers_match_result(case, scenarios, plan):
    """Числа в выгрузке совпадают с Result (Правило 3)."""
    res = evaluate_plan(case, plan, scenarios["standard"])
    df = _year_rows_df(res)
    # сверяем поступление первого года
    r0 = res.years[0]
    row0 = df[df["год"] == r0.year].iloc[0]
    assert abs(row0["поступление"] - round(r0.inflow, 3)) < 1e-6
    assert abs(row0["запас_конец"] - round(r0.stock_end, 3)) < 1e-6


def test_csv_string_has_header(case, scenarios, plan):
    res = evaluate_plan(case, plan, scenarios["standard"])
    s = result_to_csv_string(res)
    assert "год" in s
    assert "поступление" in s


def test_geopolitical_does_not_mutate_case(case, scenarios, plan):
    """Геополитический шок работает на копии - исходный case неизменен."""
    orig_price_a = case.channel("A").var_cost
    ev = GeoEvent(event_id="e", description="shock",
                  affected_channels=["A"], direction="increase", magnitude=0.25)
    run_geopolitical(case, plan, scenarios["standard"], ev)
    assert case.channel("A").var_cost == orig_price_a  # не изменилось


def test_geopolitical_increases_cost(case, scenarios, plan):
    """Рост цены каналов -> рост расходов (delta > 0)."""
    ev = GeoEvent(event_id="e", description="shock",
                  affected_channels=["A", "B"], direction="increase", magnitude=0.25)
    geo = run_geopolitical(case, plan, scenarios["standard"], ev)
    assert geo.cost_delta > 0
    # цена A выросла ровно на 25%
    assert abs(geo.price_after["A"] - geo.price_before["A"] * 1.25) < 1e-6


def test_geopolitical_decrease_direction(case, scenarios, plan):
    """Снижение цены -> множитель < 1."""
    ev = GeoEvent(event_id="e", description="drop",
                  affected_channels=["A"], direction="decrease", magnitude=0.10)
    assert abs(ev.multiplier() - 0.90) < 1e-9
    geo = run_geopolitical(case, plan, scenarios["standard"], ev)
    assert geo.cost_delta < 0
