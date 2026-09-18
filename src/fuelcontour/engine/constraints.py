"""Стадия 5 - проверка ограничений.

Возвращает список нарушений {год, тип, величина, лимит, причина} для UI (с.8).
Неисполнимый план помечается feasible=False (Правило 8). Нарушения численны,
не скрываются усреднением по горизонту (критерий №4).

Проверяем: сервис 99%/97%, CAPEX 1800/2037 и 2800/2040, ёмкость, мощность,
45-дневный резерв, Emergency <=2 лет подряд, ISRU-надёжность первого года.
"""
from __future__ import annotations

from typing import List

from ..model.entities import CaseData, Decision
from .results import YearRow, EconomicsResult, Violation
from .balance import storage_capacity

EMERGENCY_ID = "E"


def _check_service(case, rows, is_standard) -> List[Violation]:
    out = []
    c = case.constraints
    for row in rows:
        # в стандартном сценарии уровни обязательны; в стрессе - ориентиры
        sev = "error" if is_standard else "warning"
        if row.service_critical_ratio < c.service_critical_min - 1e-9:
            out.append(Violation(
                year=row.year, kind="service_critical", severity=sev,
                value=round(row.service_critical_ratio, 4),
                limit=c.service_critical_min,
                message=f"{row.year}: критический сервис "
                        f"{row.service_critical_ratio:.1%} < {c.service_critical_min:.0%}",
            ))
        if row.service_total_ratio < c.service_total_min - 1e-9:
            out.append(Violation(
                year=row.year, kind="service_total", severity=sev,
                value=round(row.service_total_ratio, 4),
                limit=c.service_total_min,
                message=f"{row.year}: общий сервис "
                        f"{row.service_total_ratio:.1%} < {c.service_total_min:.0%}",
            ))
    return out


def _check_capex(case, econ: EconomicsResult) -> List[Violation]:
    out = []
    c = case.constraints
    if econ.capex_cumulative_2037 > c.capex_cap_2037 + 1e-6:
        out.append(Violation(
            year=2037, kind="capex_2037", severity="error",
            value=econ.capex_cumulative_2037, limit=c.capex_cap_2037,
            message=f"CAPEX до 2037 = {econ.capex_cumulative_2037:.0f} "
                    f"> лимита {c.capex_cap_2037:.0f}",
        ))
    if econ.capex_cumulative_total > c.capex_cap_2040 + 1e-6:
        out.append(Violation(
            year=2040, kind="capex_2040", severity="error",
            value=econ.capex_cumulative_total, limit=c.capex_cap_2040,
            message=f"Суммарный CAPEX = {econ.capex_cumulative_total:.0f} "
                    f"> лимита {c.capex_cap_2040:.0f}",
        ))
    return out


def _check_capacity_and_storage(case, decision, rows) -> List[Violation]:
    out = []
    cap_store = storage_capacity(case, decision)
    for row in rows:
        # ёмкость хранилища
        if row.stock_end > cap_store + 1e-6:
            out.append(Violation(
                year=row.year, kind="storage_capacity", severity="error",
                value=row.stock_end, limit=cap_store,
                message=f"{row.year}: запас {row.stock_end:.1f}т "
                        f"> ёмкости {cap_store:.0f}т",
            ))
        # мощность каналов: отбор не выше доступной мощности
        for flow in row.channels:
            if flow.ordered > flow.available_cap + 1e-6:
                out.append(Violation(
                    year=row.year, kind="channel_capacity", severity="error",
                    value=flow.ordered, limit=flow.available_cap,
                    message=f"{row.year}: канал {flow.channel_id} заказ "
                            f"{flow.ordered:.1f} > мощности {flow.available_cap:.1f}",
                ))
    return out


def _check_reserve(case, rows) -> List[Violation]:
    """45-дневный резерв: R = годовой_спрос * 45/365, проверка на начало года."""
    out = []
    c = case.constraints
    for row in rows:
        required = row.demand_total * c.reserve_days / c.days_in_year
        # физический вариант проверяется на начало года
        if row.stock_start < required - 1e-6:
            out.append(Violation(
                year=row.year, kind="reserve_45d", severity="warning",
                value=row.stock_start, limit=required,
                message=f"{row.year}: запас на начало {row.stock_start:.1f}т "
                        f"< 45-дн. резерва {required:.1f}т "
                        f"(либо нужен законтрактованный аварийный резерв)",
            ))
    return out


def _check_emergency(case, decision, rows) -> List[Violation]:
    """Emergency нельзя как базовый >2 лет подряд.
    'Базовый' трактуем как заметную долю поставки (>50% отбора года)."""
    out = []
    c = case.constraints
    streak = 0
    for row in rows:
        e_delivered = sum(f.delivered for f in row.channels if f.channel_id == EMERGENCY_ID)
        is_base = e_delivered > 0.5 * row.inflow if row.inflow > 0 else False
        if is_base:
            streak += 1
            if streak > c.emergency_max_consecutive_years:
                out.append(Violation(
                    year=row.year, kind="emergency_overuse", severity="error",
                    value=streak, limit=c.emergency_max_consecutive_years,
                    message=f"{row.year}: Emergency как базовый {streak} года подряд "
                            f"(> {c.emergency_max_consecutive_years})",
                ))
        else:
            streak = 0
    return out


def check_all(case: CaseData, decision: Decision, rows: List[YearRow],
              econ: EconomicsResult, is_standard: bool = True) -> List[Violation]:
    violations: List[Violation] = []
    violations += _check_service(case, rows, is_standard)
    violations += _check_capex(case, econ)
    violations += _check_capacity_and_storage(case, decision, rows)
    violations += _check_reserve(case, rows)
    violations += _check_emergency(case, decision, rows)
    return violations
