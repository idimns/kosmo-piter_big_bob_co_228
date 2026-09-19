"""MILP-оптимизатор плана снабжения (PuLP + CBC).

Находит план с минимальными дисконтированными расходами, удовлетворяющий всем
жёстким ограничениям кейса. Это ответ на вопрос "а ваш план оптимален?" - да,
для заданной линеаризованной модели.

Переменные решения:
  order[y,c]     - отбор из канала c в год y (непрерывная >= 0)
  reserved[y,c]  - зарезервированная мощность (непрерывная >= 0)
  payable[y,c]   - облагаемый объём take-or-pay (линеаризация max)
  stock[y]       - запас на конец года
  build[i]       - бинарная: реализуем ли инвестицию i
  use_zbo        - бинарная: модернизация склада

Целевая функция: сумма дисконтированных годовых расходов.

Линеаризации:
  take-or-pay: payable >= order; payable >= top*reserved; минимизация тянет вниз
  доступность канала: order <= capacity * (доступен ? 1 : 0), гейт через build
  потери: losses = loss_rate * inflow (loss_rate зависит от use_zbo -> кусочно,
          берём консервативно через два режима склада)

Модель согласована с движком: после решения оптимизатор отдаёт обычный Decision,
который проверяется тем же evaluate_plan (Правило 3).
"""
from __future__ import annotations

from typing import Dict, List, Optional

import pulp

from ..model.entities import CaseData, ScenarioDef, Decision, ChannelDecision
from .scenario import EffectiveDemand, isru_actual_shares


# каналы, требующие инвестиции, и id инвестиций
def _investment_gate(case: CaseData, ch) -> Optional[str]:
    return ch.requires


def optimize_plan(case: CaseData, scenario: ScenarioDef,
                  use_zbo: Optional[bool] = None,
                  service_total_min: Optional[float] = None,
                  service_critical_min: Optional[float] = None,
                  margin: float = 0.01,
                  time_limit: int = 30) -> Dict:
    """Построить и решить MILP. Возвращает dict с планом и статусом.

    use_zbo=None -> оптимизатор сам решает (бинарная). Иначе фиксируется.
    service_*_min=None -> берём из ограничений кейса.
    margin - страховочный запас к порогам сервиса (оракул: план-решение делаем
             с 0.97+eps, чтобы пограничные случаи уходили в безопасную сторону;
             сам движок потом проверяет реальные 0.97).
    """
    years = case.demand.years_sorted
    channels = case.channels
    cons = case.constraints
    s_total = (service_total_min if service_total_min is not None else cons.service_total_min) + margin
    s_crit = (service_critical_min if service_critical_min is not None else cons.service_critical_min)
    s_crit = min(s_crit + margin, 1.0)
    s_total = min(s_total, 1.0)

    eff = EffectiveDemand(case, scenario)
    isru_shares = isru_actual_shares(scenario) or {}
    rate = scenario.discounting.real_rate
    base_year = scenario.discounting.base_year

    prob = pulp.LpProblem("fuel_supply", pulp.LpMinimize)

    # --- переменные ---
    order = {}
    reserved = {}
    payable = {}
    for y in years:
        for c in channels:
            order[y, c.id] = pulp.LpVariable(f"order_{y}_{c.id}", lowBound=0)
            reserved[y, c.id] = pulp.LpVariable(f"reserved_{y}_{c.id}", lowBound=0)
            payable[y, c.id] = pulp.LpVariable(f"payable_{y}_{c.id}", lowBound=0)

    stock = {y: pulp.LpVariable(f"stock_{y}", lowBound=0) for y in years}
    issued = {y: pulp.LpVariable(f"issued_{y}", lowBound=0) for y in years}
    issued_crit = {y: pulp.LpVariable(f"issued_crit_{y}", lowBound=0) for y in years}

    # инвестиции - бинарные
    build = {}
    for inv in case.investments:
        build[inv.id] = pulp.LpVariable(f"build_{inv.id}", cat="Binary")

    # ZBO
    if use_zbo is None:
        zbo_var = pulp.LpVariable("use_zbo", cat="Binary")
    else:
        zbo_var = 1 if use_zbo else 0

    # связываем zbo-режим склада с инвестицией zbo_upgrade (единый CAPEX/эффект)
    if "zbo_upgrade" in build:
        prob += build["zbo_upgrade"] == zbo_var

    # склад: ёмкость и потери зависят от zbo. линеаризуем как смесь.
    base_cap = case.storage.base.capacity
    base_loss = case.storage.base.loss_rate
    if case.storage.zbo_upgrade:
        zbo_cap = case.storage.zbo_upgrade.capacity
        zbo_loss = case.storage.zbo_upgrade.loss_rate
    else:
        zbo_cap, zbo_loss = base_cap, base_loss

    # эффективная ёмкость склада = base + (zbo-base)*zbo_var
    def storage_cap_expr():
        return base_cap + (zbo_cap - base_cap) * zbo_var

    # --- вспомогательное: доступность канала в год ---
    def channel_max(y, c):
        # доступен ли по году ввода
        if c.available_from is not None and y < c.available_from:
            return 0.0
        # канал, требующий инвестицию с датой ввода (ISRU): блокируем ПОТОК
        # до года commissioning, даже если инвестиция профинансирована раньше
        gate = _investment_gate(case, c)
        if gate is not None:
            inv = case.investment(gate)
            if inv.commissioning_from is not None and y < inv.commissioning_from:
                return 0.0
        return c.capacity

    # --- ограничения ---
    prev_stock = case.storage.base  # заглушка
    initial_stock = 0.0

    for idx, y in enumerate(years):
        # приход по каналам с учётом доступности и гейтов
        inflow_terms = []
        for c in channels:
            cmax = channel_max(y, c)
            if cmax <= 0:
                prob += order[y, c.id] == 0
                prob += reserved[y, c.id] == 0
                continue
            # мощность
            prob += order[y, c.id] <= cmax
            prob += reserved[y, c.id] <= cmax
            # take-or-pay линеаризация: payable >= order, payable >= top*reserved
            prob += payable[y, c.id] >= order[y, c.id]
            prob += payable[y, c.id] >= c.take_or_pay * reserved[y, c.id]
            # отбор не больше резерва (нельзя брать больше, чем зарезервировал)
            # для каналов без резерва (B,D,E take_or_pay=0) это тоже требует reserved>=order
            prob += order[y, c.id] <= reserved[y, c.id]

            # инвестиционный гейт: если канал требует инвестицию - order<=cmax*build
            gate = _investment_gate(case, c)
            if gate is not None and gate in build:
                prob += order[y, c.id] <= cmax * build[gate]
                # ISRU доступен только с commissioning года
            # ISRU стрессовая доля: order <= cmax * share (в стрессе)
            if c.id == "D" and y in isru_shares:
                prob += order[y, c.id] <= cmax * isru_shares[y]

            inflow_terms.append(order[y, c.id])

        inflow = pulp.lpSum(inflow_terms)
        # потери: loss_rate зависит от zbo. losses = base_loss*inflow - (base_loss-zbo_loss)*inflow*zbo
        # нелинейно (inflow*zbo). Линеаризуем консервативно: берём base_loss если zbo=0,
        # zbo_loss если zbo=1, через big-M на inflow.
        losses = pulp.LpVariable(f"losses_{y}", lowBound=0)
        M = sum(channel_max(y, c) for c in channels) + 1
        # losses >= base_loss*inflow - M*zbo  (когда zbo=0 -> losses>=base_loss*inflow)
        prob += losses >= base_loss * inflow - M * zbo_var
        # losses >= zbo_loss*inflow - M*(1-zbo) (когда zbo=1 -> losses>=zbo_loss*inflow)
        prob += losses >= zbo_loss * inflow - M * (1 - zbo_var)
        # losses <= base_loss*inflow (верхняя граница - не больше базовых потерь)
        prob += losses <= base_loss * inflow

        # баланс: stock[y] = stock_prev + inflow - losses - issued
        stock_prev = initial_stock if idx == 0 else stock[years[idx - 1]]
        prob += stock[y] == stock_prev + inflow - losses - issued[y]
        # ёмкость склада
        prob += stock[y] <= storage_cap_expr()

        # выдача не больше доступного и не больше спроса
        demand_y = eff.total(y)
        demand_crit_y = eff.critical(y)
        prob += issued[y] <= demand_y
        prob += issued[y] >= s_total * demand_y          # сервис общий
        prob += issued_crit[y] <= demand_crit_y
        prob += issued_crit[y] >= s_crit * demand_crit_y  # сервис критический
        prob += issued_crit[y] <= issued[y]               # критический часть общего

    # CAPEX ограничения (накопленные)
    capex_2037 = pulp.lpSum(inv.capex * build[inv.id] for inv in case.investments
                            if True)  # все инвестиции финансируются <=2037 в нашей модели
    prob += capex_2037 <= cons.capex_cap_2037
    prob += capex_2037 <= cons.capex_cap_2040

    # ZBO как инвестиция: если zbo_var=1, учитываем capex zbo в общем capex
    zbo_capex = case.storage.zbo_upgrade.capex if case.storage.zbo_upgrade else 0
    # (уже включено если zbo в investments; иначе добавим отдельно)

    # --- целевая функция: дисконтированные расходы ---
    cost_terms = []
    for idx, y in enumerate(years):
        t = y - base_year + 1  # end_of_year
        disc = (1 + rate) ** t
        year_cost = []
        for c in channels:
            year_cost.append(c.var_cost * payable[y, c.id])
            year_cost.append(c.reservation_rate * reserved[y, c.id])
        # хранение по среднему запасу (начало+конец)/2 - как в движке
        stock_prev = initial_stock if idx == 0 else stock[years[idx - 1]]
        year_cost.append(case.storage.base.storage_cost * 0.5 * (stock_prev + stock[y]))
        cost_terms.append(pulp.lpSum(year_cost) / disc)
    # CAPEX (в год реализации; упрощённо дисконтируем на 2037)
    capex_disc = (1 + rate) ** (2037 - base_year + 1)
    cost_terms.append(pulp.lpSum(inv.capex * build[inv.id] for inv in case.investments) / capex_disc)

    prob += pulp.lpSum(cost_terms)

    # --- решение ---
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # глушим DeprecationWarning от PuLP CBC
        solver = pulp.PULP_CBC_CMD(msg=0, timeLimit=time_limit)
        prob.solve(solver)

    status = pulp.LpStatus[prob.status]
    if status not in ("Optimal", "Feasible"):
        return {"status": status, "feasible": False, "decision": None}

    # --- извлечение решения в Decision ---
    plan: Dict[int, List[ChannelDecision]] = {}
    for y in years:
        items = []
        for c in channels:
            o = order[y, c.id].value() or 0
            r = reserved[y, c.id].value() or 0
            if o > 1e-6 or r > 1e-6:
                items.append(ChannelDecision(channel_id=c.id,
                                             reserved_capacity=round(r, 2),
                                             ordered=round(o, 2)))
        if items:
            plan[y] = items

    investments = {}
    for inv in case.investments:
        if (build[inv.id].value() or 0) > 0.5:
            # год финансирования: для ISRU надо ДО commissioning (2038) -> 2037;
            # для остальных - год доступности опциона либо 2037
            if inv.id == "isru_pilot":
                investments[inv.id] = 2037
            elif inv.available_from:
                investments[inv.id] = inv.available_from
            else:
                investments[inv.id] = 2037

    if use_zbo is not None:
        zbo_result = bool(use_zbo)
    else:
        zbo_result = (zbo_var.value() or 0) > 0.5
    # синхронизация: если склад ZBO используется, инвестиция zbo_upgrade должна
    # быть в списке (чтобы движок посчитал её CAPEX и OPEX)
    if zbo_result and "zbo_upgrade" not in investments:
        za = case.investment("zbo_upgrade")
        investments["zbo_upgrade"] = za.available_from or 2036

    decision = Decision(
        scenario_id=scenario.id,
        initial_stock=initial_stock,
        use_zbo=zbo_result,
        investments=investments,
        plan=plan,
    )

    return {
        "status": status,
        "feasible": True,
        "lower_bound": pulp.value(prob.objective),  # оценка снизу (не итоговая цена!)
        "decision": decision,
    }


def optimize_and_verify(case: CaseData, scenario: ScenarioDef,
                        use_zbo: Optional[bool] = None,
                        max_iter: int = 6, time_limit: int = 30) -> Dict:
    """Оптимизация с проверкой через движок и авто-подгонкой запаса (repair loop).

    Оракул: MILP предлагает, движок проверяет. Если движок говорит "не дотянул
    до 0.97" - увеличиваем страховочный запас и пересчитываем. Возвращаем
    engine-проверенный план + оценку снизу (lower_bound) для оценки оптимальности.
    """
    from .pipeline import evaluate_plan

    lower_bound = None
    margin = 0.005
    best = None
    for it in range(max_iter):
        res = optimize_plan(case, scenario, use_zbo=use_zbo, margin=margin,
                            time_limit=time_limit)
        if not res["feasible"]:
            margin += 0.01
            continue
        if lower_bound is None:
            # оценку снизу берём из ПЕРВОГО решения без пессимистичного запаса
            lb_res = optimize_plan(case, scenario, use_zbo=use_zbo, margin=0.0,
                                   time_limit=time_limit)
            lower_bound = lb_res.get("lower_bound")

        dec = res["decision"]
        check = evaluate_plan(case, dec, scenario)
        errors = [v for v in check.violations if v.severity == "error"]
        if not errors:
            best = {
                "status": "verified",
                "feasible": True,
                "iterations": it + 1,
                "margin": margin,
                "lower_bound": lower_bound,
                "engine_total": check.economics.total_cost,
                "engine_discounted": check.economics.total_discounted,
                "gap_pct": ((check.economics.total_discounted - lower_bound) / lower_bound * 100)
                           if lower_bound else None,
                "decision": dec,
                "result": check,
            }
            break
        # движок недоволен - усиливаем запас
        margin += 0.01

    if best is None:
        return {"status": "no_feasible_after_repair", "feasible": False,
                "decision": None, "lower_bound": lower_bound}
    return best
