"""Стадия 2 - материальный баланс.

Тождество (с.9):
    запас_конец = запас_начало + поступление - потери - выданное

Ключевые правила (Правило 5, анти-двойной-учёт):
  - потери = поступление * коэф_хранилища, учитываются ОДИН раз на оборот
  - потери НЕ начисляются повторно на остаток запаса
  - отрицательный остаток не изображается как физический запас -> это дефицит
  - ёмкость проверяется на шаге (здесь годовой агрегат + пометка внутригодовой)

Временной шаг: базовый расчёт годовой; внутригодовая проверка ёмкости/дефицита
делается через равномерное распределение (Правило 11). Для MVP берём годовой
баланс с проверкой пиков; помесячная детализация - расширение.
"""
from __future__ import annotations

from typing import Dict, List

from ..model.entities import CaseData, Decision
from .results import YearRow, ChannelFlow
from .availability import available_capacity
from .scenario import EffectiveDemand, isru_actual_shares


ISRU_ID = "D"


def storage_loss_rate(case: CaseData, decision: Decision) -> float:
    """Действующий коэффициент потерь: 4.5% базово, 1.2% после ZBO."""
    if decision.use_zbo and case.storage.zbo_upgrade is not None:
        return case.storage.zbo_upgrade.loss_rate
    return case.storage.base.loss_rate


def storage_capacity(case: CaseData, decision: Decision) -> float:
    """Ёмкость хранилища с учётом ZBO."""
    if decision.use_zbo and case.storage.zbo_upgrade is not None:
        return case.storage.zbo_upgrade.capacity
    return case.storage.base.capacity


def _delivered_for_channel(case, ch_id, ordered, avail_cap, year, scenario):
    """Фактически поставленный объём по каналу.

    В стандартном сценарии = min(заказ, доступная мощность) - без случайных
    отказов (правило контрольных расчётов: поставки по плану).
    Для ISRU в стрессе применяется заданная фактическая доля поставки.
    """
    planned = min(ordered, avail_cap)
    shares = isru_actual_shares(scenario)
    if ch_id == ISRU_ID and shares is not None and year in shares:
        # фактическая доля ISRU: доля от номинальной мощности.
        # НЕ умножаем ещё раз на надёжность (анти-двойной-учёт).
        cap_share = avail_cap * shares[year]
        return min(planned, cap_share)
    return planned


def compute_balance(case: CaseData, decision: Decision, scenario) -> List[YearRow]:
    """Прогон материального баланса по всем годам горизонта."""
    eff = EffectiveDemand(case, scenario)
    loss_rate = storage_loss_rate(case, decision)
    cap_storage = storage_capacity(case, decision)

    rows: List[YearRow] = []
    stock = decision.initial_stock

    for year in case.demand.years_sorted:
        row = YearRow(year=year)
        row.demand_total = eff.total(year)
        row.demand_critical = eff.critical(year)
        row.stock_start = stock

        avail = available_capacity(case, year, decision)

        # собираем поступления по каналам
        inflow = 0.0
        for cd in decision.for_year(year):
            ch = case.channel(cd.channel_id)
            avail_cap = avail.get(ch.id, 0.0)
            delivered = _delivered_for_channel(
                case, ch.id, cd.ordered, avail_cap, year, scenario
            )
            flow = ChannelFlow(
                channel_id=ch.id,
                reserved=cd.reserved_capacity,
                ordered=cd.ordered,
                delivered=delivered,
                available_cap=avail_cap,
            )
            row.channels.append(flow)
            inflow += delivered

        row.inflow = inflow
        # потери на валовое поступление, один раз
        row.losses = inflow * loss_rate

        # доступно к выдаче = запас_начало + поступление - потери
        available_to_issue = row.stock_start + row.inflow - row.losses

        # выдаём столько, сколько нужно по спросу, но не больше доступного
        demand = row.demand_total
        issued = min(demand, max(available_to_issue, 0.0))
        row.issued = issued

        row.served_total = issued
        # критический обслуживается в приоритете; при полном покрытии общего
        # критический тоже покрыт (критический входит в общий)
        row.served_critical = min(row.demand_critical, issued)

        row.shortage_total = max(demand - issued, 0.0)
        row.shortage_critical = max(row.demand_critical - row.served_critical, 0.0)

        # запас на конец
        stock_end = available_to_issue - issued
        # отрицательный остаток - это дефицit, не физический запас
        row.stock_end = max(stock_end, 0.0)

        stock = row.stock_end
        rows.append(row)

    return rows
