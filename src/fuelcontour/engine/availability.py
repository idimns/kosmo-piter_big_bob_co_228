"""Стадия 1 - доступность каналов.

Определяет, сколько каждый канал МОЖЕТ дать в конкретном году с учётом:
  - года ввода (available_from), напр. ISRU с 2038
  - инвестиционных гейтов (requires -> реализована ли инвестиция)
  - lead time (заказ должен быть размещён заранее)

Планируемые объёмы отделяются от фактических.
Здесь считаем доступную МОЩНОСТЬ (потолок), не фактическую поставку.
"""
from __future__ import annotations

from typing import Dict

from ..model.entities import CaseData, Channel, Decision


def channel_available(case: CaseData, ch: Channel, year: int, decision: Decision) -> bool:
    """Доступен ли канал в этом году в принципе."""
    # проверка года ввода
    if ch.available_from is not None and year < ch.available_from:
        return False

    # проверка инвестиционного гейта
    if ch.requires is not None:
        # инвестиция должна быть реализована и введена к этому году
        realized_year = decision.investments.get(ch.requires)
        if realized_year is None:
            return False
        inv = case.investment(ch.requires)
        # для ISRU важен год ввода (commissioning), для Earth-New - подготовка
        commissioning = inv.commissioning_from or realized_year
        if year < commissioning:
            return False

    return True


def available_capacity(case: CaseData, year: int, decision: Decision) -> Dict[str, float]:
    """Доступная мощность (т/год) по каждому каналу в данном году."""
    out: Dict[str, float] = {}
    for ch in case.channels:
        if channel_available(case, ch, year, decision):
            out[ch.id] = ch.capacity
        else:
            out[ch.id] = 0.0
    return out


def first_active_year(case: CaseData, ch: Channel, decision: Decision) -> int | None:
    """Первый год, когда канал реально доступен по текущему решению.
    Нужно для 'first_year' надёжности (напр. Earth-New 0.88 в первый год)."""
    for y in case.demand.years_sorted:
        if channel_available(case, ch, y, decision):
            return y
    return None
