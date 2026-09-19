"""Выгрузка результатов в CSV/XLSX.

Выгрузка содержит сценарий, периоды, единицы и допущения. Итоги совпадают с
отображаемыми результатами (Правило 3 - единый источник истины Result).

Листы XLSX:
  - plan_by_year   : план и баланс по годам
  - channels       : потоки по каналам и годам
  - economics      : экономика по годам + итоги
  - violations     : проверки ограничений
  - risks          : реестр рисков
  - meta           : сценарий, единицы, допущения
"""
from __future__ import annotations

import csv
import io as _io
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from ..engine.results import Result


UNITS = {
    "volume": "т/год",
    "money": "млн у.е. (пост. цены 2035)",
}


def _year_rows_df(res: "Result") -> pd.DataFrame:
    rows = []
    for r in res.years:
        rows.append({
            "год": r.year,
            "спрос_общий": round(r.demand_total, 3),
            "спрос_критический": round(r.demand_critical, 3),
            "запас_начало": round(r.stock_start, 3),
            "поступление": round(r.inflow, 3),
            "потери": round(r.losses, 3),
            "выдано": round(r.issued, 3),
            "запас_конец": round(r.stock_end, 3),
            "обслужен_общий": round(r.served_total, 3),
            "обслужен_критич": round(r.served_critical, 3),
            "дефицит_общий": round(r.shortage_total, 3),
            "дефицит_критич": round(r.shortage_critical, 3),
            "сервис_общий_%": round(r.service_total_ratio * 100, 2),
            "сервис_критич_%": round(r.service_critical_ratio * 100, 2),
        })
    return pd.DataFrame(rows)


def _channels_df(res: "Result") -> pd.DataFrame:
    rows = []
    for r in res.years:
        for f in r.channels:
            rows.append({
                "год": r.year,
                "канал": f.channel_id,
                "резерв_мощности": round(f.reserved, 3),
                "заказано": round(f.ordered, 3),
                "поставлено": round(f.delivered, 3),
                "доступн_мощность": round(f.available_cap, 3),
            })
    return pd.DataFrame(rows)


def _economics_df(res: "Result") -> pd.DataFrame:
    e = res.economics
    rows = []
    for r in res.years:
        y = r.year
        rows.append({
            "год": y,
            "capex": round(e.capex_by_year.get(y, 0), 3),
            "переменные": round(e.var_cost_by_year.get(y, 0), 3),
            "резерв": round(e.reservation_by_year.get(y, 0), 3),
            "take_or_pay_gap": round(e.take_or_pay_by_year.get(y, 0), 3),
            "хранение": round(e.storage_cost_by_year.get(y, 0), 3),
            "opex": round(e.opex_by_year.get(y, 0), 3),
            "итого_год": round(e.total_by_year.get(y, 0), 3),
            "дисконтир_год": round(e.discounted_by_year.get(y, 0), 3),
        })
    df = pd.DataFrame(rows)
    # строка итогов
    total_row = {
        "год": "ИТОГО",
        "capex": round(e.capex_cumulative_total, 3),
        "переменные": "", "резерв": "", "take_or_pay_gap": "",
        "хранение": "", "opex": "",
        "итого_год": round(e.total_cost, 3),
        "дисконтир_год": round(e.total_discounted, 3),
    }
    df = pd.concat([df, pd.DataFrame([total_row])], ignore_index=True)
    return df


def _violations_df(res: "Result") -> pd.DataFrame:
    if not res.violations:
        return pd.DataFrame([{"год": "", "тип": "нет нарушений", "уровень": "",
                              "значение": "", "лимит": "", "сообщение": ""}])
    rows = []
    for v in res.violations:
        rows.append({
            "год": v.year,
            "тип": v.kind,
            "уровень": v.severity,
            "значение": v.value,
            "лимит": v.limit,
            "сообщение": v.message,
        })
    return pd.DataFrame(rows)


def _risks_df(res: "Result") -> pd.DataFrame:
    if not res.risks:
        return pd.DataFrame([{"риск": "нет"}])
    rows = []
    for rk in res.risks:
        rows.append({
            "id": rk.risk_id,
            "событие": rk.event,
            "причина": rk.cause,
            "период": rk.period,
            "вероятность": rk.probability,
            "основание": rk.prob_basis,
            "ущерб_тонн": rk.impact_tons,
            "владелец": rk.owner,
            "мера": rk.mitigation,
            "остаточный": rk.residual,
        })
    return pd.DataFrame(rows)


def _meta_df(res: "Result") -> pd.DataFrame:
    data = [
        {"параметр": "сценарий", "значение": res.scenario_id},
        {"параметр": "вариант спроса", "значение": res.demand_variant},
        {"параметр": "выполнимость", "значение": "да" if res.feasible else "нет"},
        {"параметр": "единицы объёма", "значение": UNITS["volume"]},
        {"параметр": "единицы денег", "значение": UNITS["money"]},
        {"параметр": "итого расходы", "значение": round(res.economics.total_cost, 3)},
        {"параметр": "дисконтированные", "значение": round(res.economics.total_discounted, 3)},
    ]
    for note in res.notes:
        data.append({"параметр": "примечание", "значение": note})
    return pd.DataFrame(data)


def export_xlsx(res: "Result", path: str | Path) -> Path:
    """Выгрузить полный результат в XLSX (многолистовой)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(p, engine="openpyxl") as xw:
        _meta_df(res).to_excel(xw, sheet_name="meta", index=False)
        _year_rows_df(res).to_excel(xw, sheet_name="plan_by_year", index=False)
        _channels_df(res).to_excel(xw, sheet_name="channels", index=False)
        _economics_df(res).to_excel(xw, sheet_name="economics", index=False)
        _violations_df(res).to_excel(xw, sheet_name="violations", index=False)
        _risks_df(res).to_excel(xw, sheet_name="risks", index=False)
    return p


def export_csv_bundle(res: "Result", out_dir: str | Path) -> list[Path]:
    """Выгрузить в набор CSV (по листу на файл)."""
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    written = []
    sheets = {
        "plan_by_year": _year_rows_df(res),
        "channels": _channels_df(res),
        "economics": _economics_df(res),
        "violations": _violations_df(res),
        "risks": _risks_df(res),
        "meta": _meta_df(res),
    }
    for name, df in sheets.items():
        fp = d / f"{res.scenario_id}_{name}.csv"
        df.to_csv(fp, index=False, encoding="utf-8-sig")  # BOM для Excel
        written.append(fp)
    return written


def result_to_csv_string(res: "Result") -> str:
    """План по годам в CSV-строку (для API-выгрузки одним файлом)."""
    df = _year_rows_df(res)
    buf = _io.StringIO()
    df.to_csv(buf, index=False, encoding="utf-8")
    return buf.getvalue()
