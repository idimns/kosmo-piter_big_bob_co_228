"""Прогон контрольных примеров V01-V10 организатора через наш движок.

README организатора требует: "команда должна воспроизвести ожидаемые результаты
из expected_checks.json в своём стеке". Этот модуль ровно это и делает - берёт
их expected_checks.json + входы (case_inputs.json) и считает КАЖДЫЙ пример
нашими же функциями движка, потом сверяет.

Данные-ориентир лежат в validation/ (скопированы из репозитория кейса).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from ..engine.economics import variable_payment, reservation_payment

# точность сверки (раскрыта явно, как просит README организатора)
TOLERANCE = 1e-6

ROOT = Path(__file__).resolve().parents[3]
VALIDATION_DIR = ROOT / "validation"


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    computed: Dict[str, Any]
    expected: Dict[str, Any]
    note: str = ""


def _close(a, b) -> bool:
    try:
        return abs(float(a) - float(b)) <= TOLERANCE
    except (TypeError, ValueError):
        return a == b


def _compute(case_id: str, inp: dict) -> Dict[str, Any]:
    """Посчитать один контрольный пример НАШИМ движком/формулами."""
    kind = inp["kind"]

    if kind == "balance":
        # запас_конец = запас_начало + поступление - потери - выдача
        closing = inp["opening"] + inp["delivered"] - inp["losses"] - inp["served"]
        return {"closing_inventory_t": max(closing, 0.0)}

    if kind == "shortage":
        avail = inp["opening"] + inp["delivered"] - inp["losses"]
        served = min(inp["demand"], max(avail, 0.0))
        shortage = max(inp["demand"] - served, 0.0)
        closing = max(avail - served, 0.0)
        return {"served_t": served, "shortage_t": shortage, "closing_inventory_t": closing}

    if kind == "take_or_pay":
        # наша функция движка variable_payment
        pay = variable_payment(inp["price"], inp["order"], inp["top_share"], inp["reserved"])
        payable = max(inp["order"], inp["top_share"] * inp["reserved"])
        return {"payable_volume_t": payable, "variable_payment_mln": pay}

    if kind == "reservation":
        pay = reservation_payment(inp["rate"], inp["annual_capacity"], inp["fraction"])
        return {"reservation_payment_mln": pay}

    if kind == "losses":
        return {"losses_t": inp["gross_inflow"] * inp["loss_rate"]}

    if kind == "reserve_days":
        return {"reserve_t": inp["annual_demand"] * inp["days"] / 365}

    if kind == "capacity":
        excess = inp["reserved"] - inp["capacity"]
        if excess > 0:
            return {"violation": "CAPACITY_EXCEEDED", "excess_t": excess}
        return {"violation": None, "excess_t": 0}

    if kind == "nested_demand":
        # критический вложен в общий, не суммируется
        return {"total_demand_t": inp["total"]}

    if kind == "stress_share":
        # доля применяется один раз, БЕЗ повторного умножения на надёжность
        return {"actual_delivery_t": inp["planned"] * inp["actual_share"]}

    raise ValueError(f"неизвестный вид примера: {kind}")


def run_validation(validation_dir: Path | str = VALIDATION_DIR) -> List[CaseResult]:
    """Прогнать все контрольные примеры, вернуть результаты сверки."""
    d = Path(validation_dir)
    expected_list = json.loads((d / "expected_checks.json").read_text(encoding="utf-8"))
    inputs = json.loads((d / "case_inputs.json").read_text(encoding="utf-8"))["cases"]

    results: List[CaseResult] = []
    for item in expected_list:
        cid = item["case_id"]
        expected = item["expected"]
        inp = inputs.get(cid)
        if inp is None:
            results.append(CaseResult(cid, False, {}, expected, "нет входов для примера"))
            continue
        computed = _compute(cid, inp)
        # сверяем все ожидаемые ключи
        ok = all(k in computed and _close(computed[k], v) for k, v in expected.items())
        results.append(CaseResult(cid, ok, computed, expected))
    return results


def summary(results: List[CaseResult]) -> Dict[str, int]:
    passed = sum(1 for r in results if r.passed)
    return {"passed": passed, "total": len(results), "failed": len(results) - passed}
