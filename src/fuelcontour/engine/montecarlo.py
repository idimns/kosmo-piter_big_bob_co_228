"""Монте-Карло оценка рисков снабжения.

В стандартном расчёте поставки идут по плану (так требует кейс). Здесь -
отдельный вероятностный блок: разыгрываем случайные сбои каналов по их
надёжности много раз и смотрим распределение обслуженного спроса и дефицита.

ВАЖНО: это НЕ меняет базовый детерминированный расчёт. Это добавочная оценка
риска (количественная оценка рисков). Надёжность здесь применяется
ЯВНО и один раз - как вероятность сбоя канала в году, не смешивается со
стрессовым сценарием ISRU.

Воспроизводимо: результат зависит только от seed (Правило 8 / требование кейса о
детерминизме при случайных расчётах).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..model.entities import CaseData, ScenarioDef, Decision
from .balance import storage_loss_rate, storage_capacity
from .availability import available_capacity, first_active_year
from .scenario import EffectiveDemand


@dataclass
class MonteCarloResult:
    trials: int
    seed: int
    # доля прогонов, где сервис по всем годам >= порога
    prob_meets_total: float
    prob_meets_critical: float
    # статистика по суммарному дефициту за горизонт (тонны)
    mean_shortfall: float
    p50_shortfall: float
    p95_shortfall: float          # VaR-подобная величина (95-й перцентиль)
    max_shortfall: float
    # худший годовой сервис - среднее и худшее по прогонам
    mean_worst_service: float
    worst_worst_service: float
    per_year_expected_shortfall: Dict[int, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "trials": self.trials,
            "seed": self.seed,
            "prob_meets_total": round(self.prob_meets_total, 4),
            "prob_meets_critical": round(self.prob_meets_critical, 4),
            "mean_shortfall": round(self.mean_shortfall, 2),
            "p50_shortfall": round(self.p50_shortfall, 2),
            "p95_shortfall": round(self.p95_shortfall, 2),
            "max_shortfall": round(self.max_shortfall, 2),
            "mean_worst_service": round(self.mean_worst_service, 4),
            "worst_worst_service": round(self.worst_worst_service, 4),
            "per_year_expected_shortfall": {
                k: round(v, 2) for k, v in self.per_year_expected_shortfall.items()
            },
        }


def _percentile(sorted_vals: List[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = int(round(q * (len(sorted_vals) - 1)))
    return sorted_vals[idx]


def run_montecarlo(case: CaseData, decision: Decision, scenario: ScenarioDef,
                   trials: int = 2000, seed: int = 42) -> MonteCarloResult:
    """Прогнать Монте-Карло по надёжности каналов.

    В каждом прогоне для каждого канала в каждом году с вероятностью
    (1 - надёжность) считаем, что канал сбоит и поставляет долю от плана
    (упрощённо - половину; отражает частичный сбой). Затем гоняем упрощённый
    баланс и меряем дефицит.
    """
    rng = random.Random(seed)
    eff = EffectiveDemand(case, scenario)
    loss_rate = storage_loss_rate(case, decision)
    cap_storage = storage_capacity(case, decision)
    years = case.demand.years_sorted
    cons = case.constraints

    # предрасчёт: план по годам/каналам и надёжности
    fay = {c.id: first_active_year(case, c, decision) for c in case.channels}

    total_shortfalls = []
    worst_services = []
    meets_total = 0
    meets_critical = 0
    per_year_short = {y: 0.0 for y in years}

    for _ in range(trials):
        stock = decision.initial_stock
        trial_shortfall = 0.0
        worst_service = 1.0
        meets_t = True
        meets_c = True

        for year in years:
            avail = available_capacity(case, year, decision)
            inflow = 0.0
            for cd in decision.for_year(year):
                ch = case.channel(cd.channel_id)
                cap = avail.get(ch.id, 0.0)
                planned = min(cd.ordered, cap)
                rel = ch.reliability_for(year, first_active_year=fay.get(ch.id))
                # разыгрываем сбой
                if rng.random() > rel:
                    # частичный сбой - канал даёт половину планового
                    delivered = planned * 0.5
                else:
                    delivered = planned
                inflow += delivered

            losses = inflow * loss_rate
            demand = eff.total(year)
            demand_crit = eff.critical(year)
            available_to_issue = max(stock + inflow - losses, 0.0)
            issued = min(demand, available_to_issue)
            served_crit = min(demand_crit, issued)

            shortfall = max(demand - issued, 0.0)
            trial_shortfall += shortfall
            per_year_short[year] += shortfall

            serv = issued / demand if demand else 1.0
            serv_c = served_crit / demand_crit if demand_crit else 1.0
            worst_service = min(worst_service, serv)
            if serv < cons.service_total_min:
                meets_t = False
            if serv_c < cons.service_critical_min:
                meets_c = False

            stock = min(max(available_to_issue - issued, 0.0), cap_storage)

        total_shortfalls.append(trial_shortfall)
        worst_services.append(worst_service)
        if meets_t:
            meets_total += 1
        if meets_c:
            meets_critical += 1

    total_shortfalls.sort()
    return MonteCarloResult(
        trials=trials,
        seed=seed,
        prob_meets_total=meets_total / trials,
        prob_meets_critical=meets_critical / trials,
        mean_shortfall=sum(total_shortfalls) / trials,
        p50_shortfall=_percentile(total_shortfalls, 0.50),
        p95_shortfall=_percentile(total_shortfalls, 0.95),
        max_shortfall=max(total_shortfalls),
        mean_worst_service=sum(worst_services) / trials,
        worst_worst_service=min(worst_services),
        per_year_expected_shortfall={y: per_year_short[y] / trials for y in years},
    )
