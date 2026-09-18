"""Сериализация Result и данных кейса в JSON-совместимые словари для API.

Result - dataclass, отдаём фронту плоские dict'ы. Числа те же, что в ядре
(Правило 3), никакого пересчёта здесь нет.
"""
from __future__ import annotations

from typing import Dict

from ..engine.results import Result
from ..model.entities import CaseData


def result_to_dict(res: Result) -> dict:
    return {
        "scenario_id": res.scenario_id,
        "demand_variant": res.demand_variant,
        "feasible": res.feasible,
        "has_errors": res.has_errors,
        "notes": res.notes,
        "years": [
            {
                "year": r.year,
                "demand_total": r.demand_total,
                "demand_critical": r.demand_critical,
                "stock_start": r.stock_start,
                "inflow": r.inflow,
                "losses": r.losses,
                "issued": r.issued,
                "stock_end": r.stock_end,
                "served_total": r.served_total,
                "served_critical": r.served_critical,
                "shortage_total": r.shortage_total,
                "shortage_critical": r.shortage_critical,
                "service_total_ratio": r.service_total_ratio,
                "service_critical_ratio": r.service_critical_ratio,
                "channels": [
                    {
                        "channel_id": f.channel_id,
                        "reserved": f.reserved,
                        "ordered": f.ordered,
                        "delivered": f.delivered,
                        "available_cap": f.available_cap,
                    }
                    for f in r.channels
                ],
            }
            for r in res.years
        ],
        "economics": {
            "capex_by_year": res.economics.capex_by_year,
            "var_cost_by_year": res.economics.var_cost_by_year,
            "reservation_by_year": res.economics.reservation_by_year,
            "take_or_pay_by_year": res.economics.take_or_pay_by_year,
            "storage_cost_by_year": res.economics.storage_cost_by_year,
            "opex_by_year": res.economics.opex_by_year,
            "total_by_year": res.economics.total_by_year,
            "discounted_by_year": res.economics.discounted_by_year,
            "total_cost": res.economics.total_cost,
            "total_discounted": res.economics.total_discounted,
            "cost_per_ton_served": res.economics.cost_per_ton_served,
            "capex_cumulative_2037": res.economics.capex_cumulative_2037,
            "capex_cumulative_total": res.economics.capex_cumulative_total,
        },
        "violations": [
            {
                "year": v.year,
                "kind": v.kind,
                "severity": v.severity,
                "value": v.value,
                "limit": v.limit,
                "message": v.message,
            }
            for v in res.violations
        ],
        "risks": [
            {
                "risk_id": rk.risk_id,
                "event": rk.event,
                "cause": rk.cause,
                "period": rk.period,
                "probability": rk.probability,
                "prob_basis": rk.prob_basis,
                "impact_tons": rk.impact_tons,
                "owner": rk.owner,
                "mitigation": rk.mitigation,
                "residual": rk.residual,
            }
            for rk in res.risks
        ],
    }


def case_to_dict(case: CaseData) -> dict:
    """Данные кейса для отображения/редактирования во фронте.

    Помечаем статусы параметров (Правило 4): case - только чтение.
    """
    return {
        "meta": case.meta,
        "demand": {
            "status": "case",
            "years": {
                str(y): {
                    "base_total": case.demand.years[y].base_total,
                    "critical": case.demand.years[y].critical,
                    "low_total": case.demand.years[y].low_total,
                    "high_total": case.demand.years[y].high_total,
                }
                for y in case.demand.years_sorted
            },
        },
        "channels": [
            {
                "id": c.id,
                "name": c.name,
                "kind": c.kind,
                "capacity": c.capacity,
                "var_cost": c.var_cost,
                "reservation_rate": c.reservation_rate,
                "take_or_pay": c.take_or_pay,
                "lead_time_months": c.lead_time_months,
                "reliability": c.reliability,
                "available_from": c.available_from,
                "requires": c.requires,
            }
            for c in case.channels
        ],
        "storage": {
            "base": case.storage.base.model_dump(),
            "zbo_upgrade": case.storage.zbo_upgrade.model_dump() if case.storage.zbo_upgrade else None,
        },
        "investments": [inv.model_dump() for inv in case.investments],
        "constraints": case.constraints.model_dump(),
    }
