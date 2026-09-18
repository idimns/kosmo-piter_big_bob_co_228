"""Стадия 6 - риски снабжения.

ВАЖНО (Правило 6): надёжность канала живёт ЗДЕСЬ, а не в балансе. В стандартном
сценарии баланс считает поставки по плану без случайных отказов. Здесь мы
оцениваем ОЖИДАЕМЫЙ недобор из-за ненадёжности как отдельный риск-показатель.

Матсмысл выбран явно: ожидаемая недопоставка канала за год
    E[недопоставка] = поставка * (1 - надёжность)
Это НЕ вычитается из баланса (иначе двойной учёт со стрессом ISRU).
Это метрика риска для реестра и для сравнения устойчивости планов.

Источники метода: Guo et al. 2025 (resilience = вероятность покрытия спроса);
Federgruen et al. (случайная мощность/надёжность канала). См. docs/sources.md.
"""
from __future__ import annotations

from typing import List

from ..model.entities import CaseData, Decision, ScenarioDef
from .results import YearRow, RiskEntry
from .availability import first_active_year


def build_risk_register(case: CaseData, decision: Decision, rows: List[YearRow],
                        scenario: ScenarioDef) -> List[RiskEntry]:
    """Базовый реестр рисков снабжения на основе надёжности каналов.

    Команда может расширять реестр своими рисками; это автоматическая основа.
    """
    register: List[RiskEntry] = []

    # риск ненадёжности по каждому активно используемому каналу
    for ch in case.channels:
        fay = first_active_year(case, ch, decision)
        # суммарная ожидаемая недопоставка по годам
        exp_short = 0.0
        used_years = []
        for row in rows:
            flow = next((f for f in row.channels if f.channel_id == ch.id), None)
            if flow is None or flow.delivered <= 0:
                continue
            rel = ch.reliability_for(row.year, first_active_year=fay)
            exp_short += flow.delivered * (1.0 - rel)
            used_years.append(row.year)

        if not used_years:
            continue

        # средняя надёжность за годы использования (для отображения)
        rels = [ch.reliability_for(y, first_active_year=fay) for y in used_years]
        avg_rel = sum(rels) / len(rels)

        register.append(RiskEntry(
            risk_id=f"rel_{ch.id}",
            event=f"Недопоставка канала {ch.name} из-за ненадёжности",
            cause=f"надёжность канала ~{avg_rel:.2f}",
            affected_params=[f"channel.{ch.id}.delivered"],
            period=f"{used_years[0]}-{used_years[-1]}",
            probability=round(1.0 - avg_rel, 3),
            prob_basis="1 - средняя надёжность канала за годы использования",
            impact_tons=round(exp_short, 2),
            impact_service=0.0,
            owner="оператор узла",
            mitigation="резерв мощности в других каналах, аварийный запас",
            residual="частично остаётся; см. анализ чувствительности",
        ))

    return register
