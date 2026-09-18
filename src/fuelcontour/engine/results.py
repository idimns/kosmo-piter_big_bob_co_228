"""Результаты расчёта - единые структуры для всех стадий (Правило 3).

Всё, что показывает UI и выгрузка, берётся отсюда. Никаких параллельных
представлений чисел.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ChannelFlow:
    """Поток по одному каналу за год."""
    channel_id: str
    reserved: float = 0.0        # зарезервированная мощность, т/год
    ordered: float = 0.0         # заказано к отбору, т
    delivered: float = 0.0       # фактически поставлено (валовое поступление), т
    available_cap: float = 0.0   # доступная мощность в этом году, т


@dataclass
class YearRow:
    """Строка результата по одному году. Минимальное содержание модели (с.9)."""
    year: int
    demand_total: float = 0.0
    demand_critical: float = 0.0

    stock_start: float = 0.0
    inflow: float = 0.0          # валовое поступление (throughput)
    losses: float = 0.0          # потери (учтены ОДИН раз)
    issued: float = 0.0          # выдано потребителям
    stock_end: float = 0.0

    served_total: float = 0.0    # обеспеченный общий спрос
    served_critical: float = 0.0 # обеспеченный критический
    shortage_total: float = 0.0
    shortage_critical: float = 0.0

    channels: List[ChannelFlow] = field(default_factory=list)

    @property
    def service_total_ratio(self) -> float:
        return self.served_total / self.demand_total if self.demand_total else 1.0

    @property
    def service_critical_ratio(self) -> float:
        return self.served_critical / self.demand_critical if self.demand_critical else 1.0


@dataclass
class EconomicsResult:
    """Экономика по годам и суммарно."""
    capex_by_year: Dict[int, float] = field(default_factory=dict)
    var_cost_by_year: Dict[int, float] = field(default_factory=dict)
    reservation_by_year: Dict[int, float] = field(default_factory=dict)
    take_or_pay_by_year: Dict[int, float] = field(default_factory=dict)
    storage_cost_by_year: Dict[int, float] = field(default_factory=dict)
    opex_by_year: Dict[int, float] = field(default_factory=dict)

    total_by_year: Dict[int, float] = field(default_factory=dict)
    discounted_by_year: Dict[int, float] = field(default_factory=dict)

    total_cost: float = 0.0
    total_discounted: float = 0.0
    cost_per_ton_served: float = 0.0

    # сумма CAPEX для проверки лимитов
    capex_cumulative_2037: float = 0.0
    capex_cumulative_total: float = 0.0


@dataclass
class Violation:
    """Нарушение ограничения. Год, тип, величина, причина - для UI (с.8)."""
    year: Optional[int]
    kind: str                    # service_total, capex_2037, capacity, ...
    severity: str                # error | warning
    value: float
    limit: float
    message: str


@dataclass
class RiskEntry:
    """Запись реестра рисков."""
    risk_id: str
    event: str
    cause: str = ""
    affected_params: List[str] = field(default_factory=list)
    period: str = ""
    probability: Optional[float] = None
    prob_basis: str = ""
    impact_tons: float = 0.0
    impact_cost: float = 0.0
    impact_service: float = 0.0
    owner: str = ""
    mitigation: str = ""
    residual: str = ""


@dataclass
class Result:
    """Полный результат прогона одного сценария. Единый источник истины."""
    scenario_id: str
    demand_variant: str = "base"

    years: List[YearRow] = field(default_factory=list)
    economics: EconomicsResult = field(default_factory=EconomicsResult)
    violations: List[Violation] = field(default_factory=list)
    risks: List[RiskEntry] = field(default_factory=list)

    feasible: bool = True        # выполнимость плана (Правило 8)
    notes: List[str] = field(default_factory=list)

    def year(self, y: int) -> YearRow:
        for row in self.years:
            if row.year == y:
                return row
        raise KeyError(f"нет года {y} в результате")

    @property
    def has_errors(self) -> bool:
        return any(v.severity == "error" for v in self.violations)
