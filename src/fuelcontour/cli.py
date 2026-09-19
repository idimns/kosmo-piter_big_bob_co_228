"""CLI цифрового контура.

Запуск без UI (воспроизводимость для жюри, критерий №5):
    python -m fuelcontour run --scenario standard --plan results/plan_standard.json
    python -m fuelcontour compare --plan results/plan_standard.json
    python -m fuelcontour show-case

Числа CLI обязаны совпадать с числами UI и записки (Правило 3).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .io.loader import load_case, load_scenarios, load_decision
from .engine.pipeline import evaluate_plan, compare
from .model.entities import Decision

# пути по умолчанию относительно корня репо
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASE = ROOT / "data" / "case.yaml"
DEFAULT_CONFIGS = ROOT / "configs"


def _fmt_pct(x: float) -> str:
    return f"{x:.1%}"


def _print_result(res, case):
    print(f"\n=== Сценарий: {res.scenario_id} (спрос: {res.demand_variant}) ===")
    print(f"Выполнимость: {'ДА' if res.feasible else 'НЕТ (есть нарушения)'}")
    print("\nГод | Спрос | Крит | Поставка | Потери | Обсл.общ | Обсл.крит | Запас_кон")
    print("-" * 78)
    for r in res.years:
        print(f"{r.year} | {r.demand_total:6.1f} | {r.demand_critical:5.1f} | "
              f"{r.inflow:8.1f} | {r.losses:6.2f} | "
              f"{_fmt_pct(r.service_total_ratio):>8} | "
              f"{_fmt_pct(r.service_critical_ratio):>9} | {r.stock_end:7.1f}")

    e = res.economics
    print(f"\nСуммарные расходы:      {e.total_cost:10.1f} млн у.е.")
    print(f"Дисконтированные:       {e.total_discounted:10.1f} млн у.е.")
    print(f"CAPEX до 2037:          {e.capex_cumulative_2037:10.1f} (лимит 1800)")
    print(f"CAPEX суммарный:        {e.capex_cumulative_total:10.1f} (лимит 2800)")
    if e.cost_per_ton_served:
        print(f"Стоимость т обсл.спроса:{e.cost_per_ton_served:10.3f} млн у.е./т")

    if res.violations:
        print(f"\nНарушения ({len(res.violations)}):")
        for v in res.violations:
            mark = "[ERROR]" if v.severity == "error" else "[warn] "
            print(f"  {mark} {v.message}")
    else:
        print("\nНарушений нет.")

    if res.risks:
        print(f"\nРиски снабжения ({len(res.risks)}):")
        for rk in res.risks:
            print(f"  - {rk.event}: P~{rk.probability}, "
                  f"ожид.недопоставка {rk.impact_tons:.1f}т")


def _empty_decision(scenario_id: str) -> Decision:
    """Пустой план-заглушка (ничего не заказано) - для демонстрации структуры."""
    return Decision(scenario_id=scenario_id)


def cmd_run(args):
    case = load_case(args.case)
    scenarios = load_scenarios(args.configs)
    if args.scenario not in scenarios:
        print(f"Нет сценария '{args.scenario}'. Доступны: {list(scenarios)}")
        return 1

    if args.plan:
        decision = load_decision(args.plan)
    else:
        print("(план не задан, использую пустой план-заглушку)")
        decision = _empty_decision(args.scenario)

    res = evaluate_plan(case, decision, scenarios[args.scenario])
    _print_result(res, case)
    return 0


def cmd_compare(args):
    case = load_case(args.case)
    scenarios = load_scenarios(args.configs)

    if args.plan:
        decision = load_decision(args.plan)
    else:
        decision = _empty_decision("standard")

    std = evaluate_plan(case, decision, scenarios["standard"])
    strs = evaluate_plan(case, decision, scenarios["stress"])
    _print_result(std, case)
    _print_result(strs, case)

    diff = compare(std, strs)
    print("\n=== Сравнение сценариев ===")
    print(f"Расходы: standard={diff['total_cost']['standard']:.1f}, "
          f"stress={diff['total_cost']['stress']:.1f}, "
          f"delta={diff['total_cost']['delta']:+.1f}")
    return 0


def cmd_show_case(args):
    case = load_case(args.case)
    print("Каналы снабжения:")
    for c in case.channels:
        print(f"  {c.id} {c.name}: мощность {c.capacity}, цена {c.var_cost}, "
              f"ToP {c.take_or_pay:.0%}, lead {c.lead_time_months}мес")
    print("\nСпрос по годам (базовый):")
    for y in case.demand.years_sorted:
        print(f"  {y}: общий {case.demand.total(y)}, крит {case.demand.critical(y)}")
    return 0


def cmd_validate(args):
    """Прогнать контрольные примеры V01-V10 организатора через наш движок."""
    from .validation import run_validation, summary
    results = run_validation()
    print("Контрольные примеры кейса (validation/expected_checks.json):")
    print("-" * 60)
    for r in results:
        mark = "OK  " if r.passed else "FAIL"
        print(f"  {mark} {r.case_id}: {r.computed}")
        if not r.passed:
            print(f"       ожидалось: {r.expected} {r.note}")
    s = summary(results)
    print("-" * 60)
    print(f"ПРОШЛО: {s['passed']}/{s['total']}")
    return 0 if s["failed"] == 0 else 1


def build_parser():
    p = argparse.ArgumentParser(
        prog="fuelcontour",
        description="Топливный космоконтур 2035 - расчётное ядро",
    )
    p.add_argument("--case", default=str(DEFAULT_CASE), help="путь к case.yaml")
    p.add_argument("--configs", default=str(DEFAULT_CONFIGS), help="папка сценариев")

    sub = p.add_subparsers(dest="command", required=True)

    pr = sub.add_parser("run", help="прогнать план в сценарии")
    pr.add_argument("--scenario", default="standard")
    pr.add_argument("--plan", default=None, help="путь к плану JSON")
    pr.set_defaults(func=cmd_run)

    pc = sub.add_parser("compare", help="сравнить standard vs stress")
    pc.add_argument("--plan", default=None)
    pc.set_defaults(func=cmd_compare)

    ps = sub.add_parser("show-case", help="показать данные кейса")
    ps.set_defaults(func=cmd_show_case)

    pv = sub.add_parser("validate", help="прогнать контрольные примеры V01-V10")
    pv.set_defaults(func=cmd_validate)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
