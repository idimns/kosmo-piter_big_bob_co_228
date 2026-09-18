"""Конвейер расчёта - связывает 7 стадий в единый Result (Правило 3).

evaluate_plan: один сценарий -> Result
run_scenario:  загрузка сценария по id + прогон
compare:       два Result -> различия для сравнения (с.10)
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ..model.entities import CaseData, Decision, ScenarioDef
from .results import Result
from .balance import compute_balance
from .economics import compute_economics
from .constraints import check_all
from .risk import build_risk_register


def evaluate_plan(case: CaseData, decision: Decision,
                  scenario: ScenarioDef) -> Result:
    """Полный прогон одного плана в одном сценарии.

    Стадии: balance -> economics -> constraints -> risk.
    (availability и scenario-transforms вызываются внутри balance.)
    """
    is_standard = scenario.id == "standard"

    rows = compute_balance(case, decision, scenario)
    econ = compute_economics(case, decision, rows, scenario)
    violations = check_all(case, decision, rows, econ, is_standard=is_standard)
    risks = build_risk_register(case, decision, rows, scenario)

    result = Result(
        scenario_id=scenario.id,
        demand_variant=scenario.demand_variant,
        years=rows,
        economics=econ,
        violations=violations,
        risks=risks,
    )

    # выполнимость: нет ошибок-нарушений (warnings в стрессе допустимы)
    result.feasible = not result.has_errors

    if not result.feasible:
        result.notes.append(
            "План неисполним: есть нарушения уровня error. См. violations."
        )

    return result


def run_scenario(case: CaseData, decision: Decision,
                 scenarios: Dict[str, ScenarioDef], scenario_id: str) -> Result:
    """Прогнать план в сценарии по его id."""
    if scenario_id not in scenarios:
        raise KeyError(f"нет сценария '{scenario_id}'. Есть: {list(scenarios)}")
    scn = scenarios[scenario_id]
    return evaluate_plan(case, decision, scn)


def compare(standard: Result, stress: Result) -> dict:
    """Сравнение двух прогонов на общей базе (для выгрузки, с.10).

    Возвращает различия по ключевым метрикам год-к-году и суммарно.
    """
    diff = {
        "scenarios": [standard.scenario_id, stress.scenario_id],
        "total_cost": {
            standard.scenario_id: standard.economics.total_cost,
            stress.scenario_id: stress.economics.total_cost,
            "delta": stress.economics.total_cost - standard.economics.total_cost,
        },
        "total_discounted": {
            standard.scenario_id: standard.economics.total_discounted,
            stress.scenario_id: stress.economics.total_discounted,
            "delta": stress.economics.total_discounted - standard.economics.total_discounted,
        },
        "feasible": {
            standard.scenario_id: standard.feasible,
            stress.scenario_id: stress.feasible,
        },
        "by_year": [],
    }

    years = [r.year for r in standard.years]
    for y in years:
        srow = standard.year(y)
        try:
            trow = stress.year(y)
        except KeyError:
            continue
        diff["by_year"].append({
            "year": y,
            "service_total": {
                "standard": round(srow.service_total_ratio, 4),
                "stress": round(trow.service_total_ratio, 4),
            },
            "service_critical": {
                "standard": round(srow.service_critical_ratio, 4),
                "stress": round(trow.service_critical_ratio, 4),
            },
            "shortage_total": {
                "standard": round(srow.shortage_total, 2),
                "stress": round(trow.shortage_total, 2),
            },
            "stock_end": {
                "standard": round(srow.stock_end, 2),
                "stress": round(trow.stock_end, 2),
            },
        })

    return diff
