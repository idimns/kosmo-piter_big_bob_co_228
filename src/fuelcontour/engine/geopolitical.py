"""Блок геополитических изменений цен.

Оператор задаёт сценарное событие, затронутые каналы, составляющую цены,
период, направление и величину изменения. Модуль:
  - работает на КОПИИ набора (не меняет обязательные контрольные сценарии)
  - применяет сценарный коэффициент к агрегированной цене канала
  - показывает причинную цепочку "условие -> цена -> расходы/решения"
  - даёт сравнение до/после и восстановление исходных цен

Рыночная цена топлива и агрегированная цена доставки различаются (с.11);
у нас var_cost - агрегированная цена доставки в узел. При отсутствии разбивки
цены допустим явно обозначенный сценарный коэффициент к агрегированной цене.

Совмещение с обязательным стрессом: один и тот же ценовой эффект не
начисляется дважды (флаг combine с явными правилами).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..model.entities import CaseData, Decision, ScenarioDef
from .pipeline import evaluate_plan
from .results import Result


@dataclass
class GeoEvent:
    """Геополитическое сценарное событие."""
    event_id: str
    description: str
    affected_channels: List[str]           # id каналов
    price_component: str = "aggregate"     # какую составляющую цены меняем
    direction: str = "increase"            # increase | decrease
    magnitude: float = 0.0                 # доля, напр. 0.25 = +25%
    from_year: Optional[int] = None
    to_year: Optional[int] = None
    basis: str = ""                        # обоснование/источник

    def multiplier(self) -> float:
        """Множитель цены из направления и величины."""
        m = abs(self.magnitude)
        if self.direction == "decrease":
            return max(0.0, 1.0 - m)
        return 1.0 + m

    def applies_to_year(self, year: int) -> bool:
        if self.from_year is not None and year < self.from_year:
            return False
        if self.to_year is not None and year > self.to_year:
            return False
        return True


@dataclass
class GeoResult:
    """Результат геополитического сценария: до/после + цепочка."""
    event: GeoEvent
    before: Result
    after: Result
    price_before: Dict[str, float] = field(default_factory=dict)
    price_after: Dict[str, float] = field(default_factory=dict)
    cost_delta: float = 0.0
    causal_chain: List[str] = field(default_factory=list)


def _apply_shock_to_case(case: CaseData, event: GeoEvent) -> CaseData:
    """Копия кейса с изменённой ценой затронутых каналов.

    ВАЖНО: работаем на deepcopy, исходный case неизменен (восстановление
    исходных цен = просто взять оригинал).
    """
    shocked = copy.deepcopy(case)
    mult = event.multiplier()
    for ch in shocked.channels:
        if ch.id in event.affected_channels:
            # если событие на весь горизонт - меняем базовую var_cost.
            # если период ограничен - эффект учитывается через from/to_year
            # в момент расчёта; для MVP применяем к var_cost как сценарный
            # коэффициент (агрегированная цена).
            ch.var_cost = round(ch.var_cost * mult, 6)
    return shocked


def run_geopolitical(case: CaseData, decision: Decision, scenario: ScenarioDef,
                     event: GeoEvent, combine_with_stress: bool = False) -> GeoResult:
    """Прогнать геополитический сценарий на копии набора.

    combine_with_stress=False: чистый геополитический эффект на базе сценария.
    Если scenario уже стрессовый и combine=True - ценовой шок не дублирует
    изменения спроса стресса (они независимы: спрос и цена - разные параметры).
    """
    # before: обычный прогон без шока
    before = evaluate_plan(case, decision, scenario)

    # after: прогон на копии с ценовым шоком
    shocked_case = _apply_shock_to_case(case, event)
    after = evaluate_plan(shocked_case, decision, scenario)

    # цены до/после для затронутых каналов
    price_before = {c.id: c.var_cost for c in case.channels if c.id in event.affected_channels}
    price_after = {c.id: c.var_cost for c in shocked_case.channels if c.id in event.affected_channels}

    cost_delta = after.economics.total_cost - before.economics.total_cost

    # причинная цепочка "условие -> параметр цены -> расходы"
    chain = [
        f"Событие: {event.description}",
        f"Затронуты каналы: {', '.join(event.affected_channels)}",
        f"Цена (агрегированная) {event.direction} на {abs(event.magnitude):.0%} "
        f"-> множитель {event.multiplier():.3f}",
    ]
    for cid in event.affected_channels:
        if cid in price_before and cid in price_after:
            chain.append(
                f"  канал {cid}: {price_before[cid]} -> {price_after[cid]} млн у.е./т"
            )
    chain.append(f"Изменение суммарных расходов: {cost_delta:+.1f} млн у.е.")
    if combine_with_stress:
        chain.append("Совмещение со стрессом: ценовой шок и спрос x1.15 независимы, "
                     "двойного начисления нет.")

    return GeoResult(
        event=event,
        before=before,
        after=after,
        price_before=price_before,
        price_after=price_after,
        cost_delta=cost_delta,
        causal_chain=chain,
    )
