"""Анализ чувствительности: как результат плана зависит от параметров.

Прогоняем один и тот же план через движок, варьируя по сетке ключевые параметры
(цена канала A, доли поставки ISRU, множитель спроса). Возвращаем поверхность
"параметр -> суммарные расходы / худший сервис".

Детерминировано (без случайности). Работает на копии кейса, исходные данные не
меняются.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Dict, List, Callable

from ..model.entities import CaseData, ScenarioDef, Decision
from .pipeline import evaluate_plan


@dataclass
class SensitivityPoint:
    param_value: float
    total_cost: float
    total_discounted: float
    worst_service_total: float
    worst_service_critical: float
    feasible: bool


@dataclass
class SensitivityResult:
    param_name: str
    points: List[SensitivityPoint] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "param_name": self.param_name,
            "points": [
                {
                    "value": p.param_value,
                    "total_cost": round(p.total_cost, 1),
                    "total_discounted": round(p.total_discounted, 1),
                    "worst_service_total": round(p.worst_service_total, 4),
                    "worst_service_critical": round(p.worst_service_critical, 4),
                    "feasible": p.feasible,
                }
                for p in self.points
            ],
        }


def _run(case: CaseData, decision: Decision, scenario: ScenarioDef) -> SensitivityPoint:
    r = evaluate_plan(case, decision, scenario)
    worst_t = min((row.service_total_ratio for row in r.years), default=1.0)
    worst_c = min((row.service_critical_ratio for row in r.years), default=1.0)
    return SensitivityPoint(
        param_value=0.0,  # заполнит вызывающий
        total_cost=r.economics.total_cost,
        total_discounted=r.economics.total_discounted,
        worst_service_total=worst_t,
        worst_service_critical=worst_c,
        feasible=r.feasible,
    )


def sweep_channel_price(case: CaseData, decision: Decision, scenario: ScenarioDef,
                        channel_id: str, multipliers: List[float]) -> SensitivityResult:
    """Как меняются расходы/сервис при изменении цены канала (×multiplier)."""
    out = SensitivityResult(param_name=f"price_{channel_id}_mult")
    base_price = case.channel(channel_id).var_cost
    for m in multipliers:
        c2 = copy.deepcopy(case)
        c2.channel(channel_id).var_cost = base_price * m
        pt = _run(c2, decision, scenario)
        pt.param_value = m
        out.points.append(pt)
    return out


def sweep_demand(case: CaseData, decision: Decision, scenario: ScenarioDef,
                 multipliers: List[float]) -> SensitivityResult:
    """Множитель спроса ко всем годам (сверх сценарного)."""
    out = SensitivityResult(param_name="demand_mult")
    for m in multipliers:
        c2 = copy.deepcopy(case)
        for y in c2.demand.years:
            dy = c2.demand.years[y]
            dy.base_total *= m
            dy.critical *= m
            dy.low_total *= m
            dy.high_total *= m
        pt = _run(c2, decision, scenario)
        pt.param_value = m
        out.points.append(pt)
    return out


def sweep_isru_reliability(case: CaseData, decision: Decision, scenario: ScenarioDef,
                           first_year_values: List[float]) -> SensitivityResult:
    """Надёжность ISRU (канал D) первого года - влияет через блок рисков."""
    out = SensitivityResult(param_name="isru_first_year_reliability")
    for v in first_year_values:
        c2 = copy.deepcopy(case)
        d = c2.channel("D")
        # меняем первое доступное значение профиля надёжности
        key = min((k for k in d.reliability if k.isdigit()), default="default")
        d.reliability[key] = v
        pt = _run(c2, decision, scenario)
        pt.param_value = v
        out.points.append(pt)
    return out


def tornado(case: CaseData, decision: Decision, scenario: ScenarioDef,
            delta: float = 0.2) -> dict:
    """Торнадо-анализ: вклад ±delta каждого параметра в суммарные расходы.

    Возвращает по каждому фактору расходы при -delta и +delta от базы.
    Показывает, какой параметр двигает результат сильнее всего.
    """
    base = _run(case, decision, scenario).total_cost

    factors: Dict[str, dict] = {}

    for ch_id in ["A", "B"]:
        low = sweep_channel_price(case, decision, scenario, ch_id, [1 - delta]).points[0]
        high = sweep_channel_price(case, decision, scenario, ch_id, [1 + delta]).points[0]
        factors[f"price_{ch_id}"] = {
            "low": round(low.total_cost, 1),
            "high": round(high.total_cost, 1),
            "swing": round(abs(high.total_cost - low.total_cost), 1),
        }

    dlow = sweep_demand(case, decision, scenario, [1 - delta]).points[0]
    dhigh = sweep_demand(case, decision, scenario, [1 + delta]).points[0]
    factors["demand"] = {
        "low": round(dlow.total_cost, 1),
        "high": round(dhigh.total_cost, 1),
        "swing": round(abs(dhigh.total_cost - dlow.total_cost), 1),
    }

    # сортируем по влиянию (swing)
    ordered = dict(sorted(factors.items(), key=lambda kv: kv[1]["swing"], reverse=True))
    return {"base_cost": round(base, 1), "factors": ordered}
