"""
Сущности модели - pydantic-схемы для данных кейса, сценариев и решений.

Три статуса параметра (Правило 4):
    CASE       - исходное условие, неизменно в контрольных расчётах
    DECISION   - решение пользователя
    ASSUMPTION - допущение команды

Здесь только структуры данных. Вся расчётная логика - в engine/.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional, Dict, List, Literal

from pydantic import BaseModel, Field, field_validator


class ParamStatus(str, Enum):
    CASE = "case"
    DECISION = "decision"
    ASSUMPTION = "assumption"


# --- спрос -------------------------------------------------------------------

class DemandYear(BaseModel):
    base_total: float
    critical: float
    low_total: float
    high_total: float

    @field_validator("critical")
    @classmethod
    def critical_within_total(cls, v, info):
        # критический входит в общий, не может его превышать
        base = info.data.get("base_total")
        if base is not None and v > base:
            raise ValueError(f"критический спрос {v} > общего {base}")
        return v


class Demand(BaseModel):
    status: ParamStatus = ParamStatus.CASE
    years: Dict[int, DemandYear]

    def total(self, year: int, variant: str = "base") -> float:
        """Общий спрос за год по варианту (base/low/high)."""
        d = self.years[year]
        if variant == "base":
            return d.base_total
        elif variant == "low":
            return d.low_total
        elif variant == "high":
            return d.high_total
        raise ValueError(f"неизвестный вариант спроса: {variant}")

    def critical(self, year: int, variant: str = "base") -> float:
        """Критический спрос. В low/high доля критического сохраняется
        от базового года (правило контрольных расчётов, с.6)."""
        d = self.years[year]
        if variant == "base":
            return d.critical
        # пропорция от изменения общего спроса
        share = d.critical / d.base_total if d.base_total else 0.0
        return self.total(year, variant) * share

    @property
    def years_sorted(self) -> List[int]:
        return sorted(self.years.keys())


# --- каналы ------------------------------------------------------------------

class Channel(BaseModel):
    id: str
    name: str
    kind: str = ""
    capacity: float                      # т/год
    var_cost: float                      # млн у.е./т
    reservation_rate: float              # млн у.е. за (т/год)
    take_or_pay: float                   # доля [0..1]
    lead_time_months: float
    reliability: Dict[str, float]        # {first_year, default} или {default}
    available_from: Optional[int] = None
    requires: Optional[str] = None

    @field_validator("reliability", mode="before")
    @classmethod
    def coerce_reliability_keys(cls, v):
        # YAML отдаёт годы как int (2038:), а first_year/default - строки.
        # приводим всё к строкам, чтобы ключи были однородны
        if isinstance(v, dict):
            return {str(k): val for k, val in v.items()}
        return v

    def reliability_for(self, year: int, first_active_year: Optional[int] = None) -> float:
        """Надёжность канала в данном году.
        first_active_year - год ввода канала (для 'first_year' ставки).
        ВНИМАНИЕ: используется ТОЛЬКО в блоке рисков, не как множитель объёма!
        """
        rel = self.reliability
        if first_active_year is not None and year == first_active_year:
            if "first_year" in rel:
                return rel["first_year"]
        # ISRU задан по абсолютным годам
        ykey = str(year)
        if ykey in rel:
            return rel[ykey]
        return rel.get("default", 1.0)


# --- хранилище ---------------------------------------------------------------

class StorageMode(BaseModel):
    capacity: float
    loss_rate: float                     # доля от throughput
    storage_cost: Optional[float] = None
    extra_opex: float = 0.0
    capex: float = 0.0


class Storage(BaseModel):
    status: ParamStatus = ParamStatus.CASE
    base: StorageMode
    zbo_upgrade: Optional[StorageMode] = None


# --- инвестиции --------------------------------------------------------------

class Investment(BaseModel):
    id: str
    name: str
    capex: float
    available_from: Optional[int] = None
    finance_before: Optional[int] = None
    commissioning_from: Optional[int] = None
    extra_opex: float = 0.0
    capex_breakdown: Optional[Dict[str, float]] = None
    effect: str = ""


# --- ограничения -------------------------------------------------------------

class Constraints(BaseModel):
    status: ParamStatus = ParamStatus.CASE
    service_critical_min: float = 0.99
    service_total_min: float = 0.97
    capex_cap_2037: float = 1800
    capex_cap_2040: float = 2800
    reserve_days: int = 45
    days_in_year: int = 365
    emergency_max_consecutive_years: int = 2
    isru_first_year_reliability_cap: float = 0.78


# --- корневой контейнер данных кейса -----------------------------------------

class CaseData(BaseModel):
    meta: dict = Field(default_factory=dict)
    demand: Demand
    channels_status: ParamStatus = ParamStatus.CASE
    channels: List[Channel]
    storage: Storage
    investments: List[Investment]
    constraints: Constraints

    def channel(self, cid: str) -> Channel:
        for c in self.channels:
            if c.id == cid:
                return c
        raise KeyError(f"нет канала {cid}")

    def investment(self, iid: str) -> Investment:
        for inv in self.investments:
            if inv.id == iid:
                return inv
        raise KeyError(f"нет инвестиции {iid}")


# --- сценарий ----------------------------------------------------------------

class Transform(BaseModel):
    type: str
    # поля зависят от типа; храним гибко
    from_year: Optional[int] = None
    factor: Optional[float] = None
    applies_to: Optional[List[str]] = None
    shares: Optional[Dict[int, float]] = None


class Discounting(BaseModel):
    real_rate: float = 0.07
    moment: Literal["end_of_year", "start_of_year", "mid_year"] = "end_of_year"
    base_year: int = 2035


class ScenarioDef(BaseModel):
    id: str
    name: str
    description: str = ""
    demand_variant: str = "base"
    transforms: List[Transform] = Field(default_factory=list)
    discounting: Discounting = Field(default_factory=Discounting)


# --- решения пользователя ----------------------------------------------------

class ChannelDecision(BaseModel):
    """Решение по одному каналу в одном году."""
    channel_id: str
    reserved_capacity: float = 0.0       # зарезервированная мощность, т/год
    ordered: float = 0.0                 # заказанный к отбору объём, т

    @field_validator("reserved_capacity", "ordered")
    @classmethod
    def non_negative(cls, v):
        if v < 0:
            raise ValueError("объём/резерв не может быть отрицательным")
        return v


class Decision(BaseModel):
    """Полное решение оператора: что заказываем, что резервируем,
    какие инвестиции реализуем и когда.
    Это DECISION-слой (Правило 4) - меняется через интерфейс/конфиг.
    """
    scenario_id: str = "standard"
    initial_stock: float = 0.0           # начальный запас (задаётся явно)
    # по годам -> список решений по каналам
    plan: Dict[int, List[ChannelDecision]] = Field(default_factory=dict)
    # реализованные инвестиции: id -> год реализации/финансирования
    investments: Dict[str, int] = Field(default_factory=dict)
    use_zbo: bool = False

    def for_year(self, year: int) -> List[ChannelDecision]:
        return self.plan.get(year, [])
