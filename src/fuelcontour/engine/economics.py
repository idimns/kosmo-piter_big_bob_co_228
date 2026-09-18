"""Стадия 4 - экономика.

Ключевые формулы (правила контрольных расчётов, с.7):

  переменный_платёж = цена * max(отбор, take_or_pay * зарезерв_мощность)
  резерв_платёж (полный год) = тариф * зарезерв_мощность(т/год)
  резерв_платёж (часть года) пропорционален длительности
  хранение = storage_cost * средний_физ_запас_по_времени

Анти-двойной-учёт (Правило 5):
  - take_or_pay НЕ прибавляется второй раз к уже оплаченному минимуму
    (max, а не сумма)
  - стоимость потерь НЕ дублируется поверх оплаченного восполняющего топлива
  - зарезервированная мощность периода = мощность(т/год) * длительность(годы)

Все суммы в постоянных ценах 2035. Дисконтирование по раскрытой ставке.
"""
from __future__ import annotations

from typing import Dict, List

from ..model.entities import CaseData, Decision, ScenarioDef
from .results import YearRow, EconomicsResult
from .balance import storage_capacity


def variable_payment(price: float, drawn: float, take_or_pay: float,
                     reserved_capacity: float) -> float:
    """Переменный платёж за канал за год.

    price * max(отобранный объём, ToP-доля * зарезервированная мощность).
    ToP не прибавляется вторым разом - именно max (с.7).
    """
    top_min = take_or_pay * reserved_capacity
    billable = max(drawn, top_min)
    return price * billable


def reservation_payment(rate: float, reserved_capacity: float,
                        year_fraction: float = 1.0) -> float:
    """Плата за резерв мощности.

    Табличный тариф - годовая ставка за единицу годовой мощности.
    Полный год: тариф * мощность. Часть года: пропорционально.
    """
    return rate * reserved_capacity * year_fraction


def take_or_pay_gap(price: float, drawn: float, take_or_pay: float,
                    reserved_capacity: float) -> float:
    """Та часть платежа, что оплачена сверх фактического отбора (ToP-штраф).
    Для отчётности: показать, сколько заплачено за неиспользованный минимум.
    Не добавляется к расходам отдельно - уже сидит в variable_payment.
    """
    top_min = take_or_pay * reserved_capacity
    if top_min > drawn:
        return price * (top_min - drawn)
    return 0.0


def _avg_physical_stock(row: YearRow) -> float:
    """Средний физический запас за год (по времени).

    Способ усреднения раскрывается (с.6): берём среднее начала и конца года
    как простейшую линейную аппроксимацию равномерного оборота.
    """
    return (row.stock_start + row.stock_end) / 2.0


def _capex_schedule(case: CaseData, decision: Decision) -> Dict[int, float]:
    """CAPEX по годам согласно реализованным инвестициям и их датам."""
    sched: Dict[int, float] = {}
    for inv_id, year in decision.investments.items():
        inv = case.investment(inv_id)
        # финансируем в год реализации (для ISRU - до commissioning)
        finance_year = year
        if inv.finance_before is not None:
            # должно быть профинансировано до этого года; берём год решения
            finance_year = min(year, inv.finance_before - 1) if year >= inv.finance_before else year
        sched[finance_year] = sched.get(finance_year, 0.0) + inv.capex
    return sched


def _opex_for_year(case: CaseData, decision: Decision, year: int) -> float:
    """Дополнительный постоянный OPEX после ввода (ZBO, ISRU)."""
    opex = 0.0
    for inv_id, ry in decision.investments.items():
        inv = case.investment(inv_id)
        start = inv.commissioning_from or ry
        if year >= start:
            opex += inv.extra_opex
    # ZBO OPEX учитываем через инвестицию zbo_upgrade (extra_opex там же)
    return opex


def compute_economics(case: CaseData, decision: Decision, rows: List[YearRow],
                      scenario: ScenarioDef) -> EconomicsResult:
    econ = EconomicsResult()
    rate = scenario.discounting.real_rate
    base_year = scenario.discounting.base_year

    capex_sched = _capex_schedule(case, decision)

    for row in rows:
        year = row.year
        var_total = 0.0
        res_total = 0.0
        top_total = 0.0

        for flow in row.channels:
            ch = case.channel(flow.channel_id)
            var_total += variable_payment(
                ch.var_cost, flow.delivered, ch.take_or_pay, flow.reserved
            )
            res_total += reservation_payment(ch.reservation_rate, flow.reserved)
            top_total += take_or_pay_gap(
                ch.var_cost, flow.delivered, ch.take_or_pay, flow.reserved
            )

        # хранение по среднему физическому запасу
        storage_cost_rate = case.storage.base.storage_cost or 0.72
        storage_total = storage_cost_rate * _avg_physical_stock(row)

        capex = capex_sched.get(year, 0.0)
        opex = _opex_for_year(case, decision, year)

        econ.capex_by_year[year] = capex
        econ.var_cost_by_year[year] = var_total
        econ.reservation_by_year[year] = res_total
        econ.take_or_pay_by_year[year] = top_total
        econ.storage_cost_by_year[year] = storage_total
        econ.opex_by_year[year] = opex

        # суммарные расходы года. ToP уже внутри var_total (max), не плюсуем.
        year_total = capex + var_total + res_total + storage_total + opex
        econ.total_by_year[year] = year_total

        # дисконтирование на конец года (по умолчанию)
        t = year - base_year
        if scenario.discounting.moment == "end_of_year":
            t = year - base_year + 1
        elif scenario.discounting.moment == "mid_year":
            t = year - base_year + 0.5
        disc = year_total / ((1 + rate) ** t)
        econ.discounted_by_year[year] = disc

    econ.total_cost = sum(econ.total_by_year.values())
    econ.total_discounted = sum(econ.discounted_by_year.values())

    # накопленный CAPEX для проверки лимитов
    econ.capex_cumulative_2037 = sum(
        c for y, c in econ.capex_by_year.items() if y <= 2037
    )
    econ.capex_cumulative_total = sum(econ.capex_by_year.values())

    # стоимость тонны фактически обслуженного спроса
    total_served = sum(r.served_total for r in rows)
    if total_served > 0:
        econ.cost_per_ton_served = econ.total_cost / total_served

    return econ
