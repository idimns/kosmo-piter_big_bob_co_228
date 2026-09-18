"""Стадия 7 (частично) - применение сценарных трансформаций.

Стандартный сценарий: данные как есть.
Стрессовый: с 2038 спрос x1.15, ISRU по фактическим долям.

Изоляция сценариев (с.7): каждый сценарий со своим id и списком изменений,
всегда можно вернуться к исходным данным (мы не мутируем CaseData).
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from ..model.entities import CaseData, ScenarioDef


class EffectiveDemand:
    """Спрос после применения трансформаций сценария.
    Не трогает исходный CaseData - считает на лету.
    """
    def __init__(self, case: CaseData, scenario: ScenarioDef):
        self.case = case
        self.scenario = scenario
        self.variant = scenario.demand_variant
        # собираем множители спроса по годам из трансформаций
        self._mult: Dict[int, float] = {}
        self._build_multipliers()

    def _build_multipliers(self):
        for t in self.scenario.transforms:
            if t.type == "demand_multiplier":
                fy = t.from_year or self.case.demand.years_sorted[0]
                for y in self.case.demand.years_sorted:
                    if y >= fy:
                        self._mult[y] = self._mult.get(y, 1.0) * (t.factor or 1.0)

    def total(self, year: int) -> float:
        base = self.case.demand.total(year, self.variant)
        return base * self._mult.get(year, 1.0)

    def critical(self, year: int) -> float:
        base = self.case.demand.critical(year, self.variant)
        return base * self._mult.get(year, 1.0)


def isru_actual_shares(scenario: ScenarioDef) -> Optional[Dict[int, float]]:
    """Фактические доли поставки ISRU в стрессе (если заданы).

    Эти доли применяются к номинальной мощности ISRU напрямую и НЕ
    умножаются повторно на коэффициент надёжности (правило контрольных
    расчётов, с.6: один механизм недопоставки не учитывается дважды).
    """
    for t in scenario.transforms:
        if t.type == "isru_actual_supply" and t.shares:
            # ключи-годы приходят из YAML как int
            return {int(k): v for k, v in t.shares.items()}
    return None
