"""Гибкий импорт данных кейса из CSV/XLSX без строгой структуры.

Идея: файл может прийти с разными названиями колонок, в любом порядке, на
любом листе (для xlsx), с лишними колонками. Импортёр:
  1. читает таблицу (CSV или XLSX, автоопределение листа с данными)
  2. нормализует заголовки и по словарю синонимов угадывает роль каждой колонки
  3. определяет ТИП таблицы (спрос / каналы / хранилище / инвестиции / ограничения)
  4. отдаёт превью + предложенный маппинг, чтобы пользователь мог поправить
  5. по подтверждённому маппингу собирает куски CaseData

Формат-ориентир - репозиторий организатора SpaceEconomyPolicy/test_oil
(demand.csv, supply_sources.csv, ...), но жёсткой привязки к нему нет.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

import pandas as pd


# ---------------------------------------------------------------------------
# нормализация заголовков
# ---------------------------------------------------------------------------

def norm(s: Any) -> str:
    """Привести заголовок к каноническому виду для сравнения.
    'Capacity (t/year)' -> 'capacity t year', 'Take-or-Pay' -> 'take or pay'.
    """
    s = str(s).strip().lower()
    s = s.replace("ё", "е")
    # убираем единицы в скобках и мусорную пунктуацию -> пробелы
    s = re.sub(r"[\(\)\[\]\{\}]", " ", s)
    s = re.sub(r"[_\-/\\.,;:]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


# словари синонимов для каждой роли поля. ключ - канонич. роль, значения -
# подстроки/слова, которые в ней встречаются (в нормализованном виде).
# матчинг по вхождению токенов, не по точному равенству.
FIELD_SYNONYMS: Dict[str, List[str]] = {
    # --- общие ---
    "year": ["year", "год"],
    "id": ["source id", "id", "channel id", "код", "ид", "storage id", "investment id", "constraint id"],
    "name": ["name", "channel", "название", "наименование", "канал", "имя", "mode"],
    # --- спрос ---
    "base_total": ["base total", "базовый общий", "общий", "total demand", "base demand", "спрос общий", "base total t"],
    "critical": ["critical", "критический", "base critical", "крит", "critical t"],
    "low_total": ["low total", "низкий", "low", "low demand", "низкий общий"],
    "high_total": ["high total", "высокий", "high", "high demand", "высокий общий"],
    # --- каналы ---
    "capacity": ["capacity", "мощность", "capacity t per year", "cap", "макс мощность", "capacity t"],
    "var_cost": ["variable cost", "переменная стоимость", "var cost", "цена", "стоимость т", "cost mln per t", "variable cost mln per t"],
    "reservation_rate": ["reservation rate", "резерв", "плата за резерв", "reservation", "ставка резерва", "reservation rate mln per t year capacity"],
    "take_or_pay": ["take or pay", "top", "take or pay share", "обязательство", " top "],
    "lead_time_months": ["lead time", "срок", "lead", "lead time min value", "lead time value"],
    "lead_time_min": ["lead time min value", "lead min", "срок мин"],
    "lead_time_max": ["lead time max value", "lead max", "срок макс"],
    "lead_time_unit": ["lead time unit", "unit срок", "единица срока"],
    "reliability": ["reliability", "надежность", "reliability profile", "reliability input", "профиль надежности"],
    "available_from": ["available from", "доступен с", "available from year", "год ввода", "с года"],
    "requires": ["requires", "требует", "нужна инвестиция", "gate"],
    # --- хранилище ---
    "loss_rate": ["loss rate", "потери", "loss rate on throughput", "коэффициент потерь"],
    "storage_cost": ["holding cost", "хранение", "storage cost", "holding cost mln per t year", "стоимость хранения"],
    "capex": ["capex", "капвложения", "capex mln", "total capex mln", "total capex", "полный capex"],
    "extra_opex": ["opex", "fixed opex", "доп opex", "fixed opex mln per year", "additional opex"],
    "option_fee": ["option fee", "плата за опцион", "option fee mln"],
    "exercise_cost": ["exercise cost", "реализация", "exercise cost mln"],
    "commissioning_rule": ["commissioning", "ввод", "commissioning rule", "правило ввода"],
    # --- ограничения ---
    "metric": ["metric", "метрика", "показатель"],
    "operator": ["operator", "оператор", "знак", "op"],
    "value": ["value", "значение", "порог"],
    "unit": ["unit", "единица", "ед"],
    "period": ["period", "период"],
    "scenario": ["scenario", "сценарий"],
    "severity": ["severity", "уровень", "жесткость"],
}


def guess_role(header: str) -> Optional[str]:
    """Угадать роль колонки по заголовку. Возвращает роль или None.

    Матчим по самому длинному совпавшему синониму (чтобы 'base critical'
    выиграл у 'critical' и т.п.). Возвращаем роль с самым специфичным матчем.
    """
    h = norm(header)
    best_role = None
    best_len = 0
    for role, syns in FIELD_SYNONYMS.items():
        for syn in syns:
            sn = syn.strip()
            # совпадение как отдельное вхождение токена/фразы
            if sn and (h == sn or (" " + sn + " ") in (" " + h + " ")):
                if len(sn) > best_len:
                    best_len = len(sn)
                    best_role = role
    return best_role


# ---------------------------------------------------------------------------
# определение типа таблицы
# ---------------------------------------------------------------------------

TABLE_SIGNATURES = {
    # тип -> набор ролей, наличие которых характерно
    "demand": {"year", "base_total"},
    "channels": {"capacity", "var_cost"},
    "storage": {"loss_rate", "storage_cost"},
    "investments": {"capex"},
    "constraints": {"metric", "value", "operator"},
}


def detect_table_type(roles: List[str]) -> Optional[str]:
    """По набору распознанных ролей определить тип таблицы."""
    roleset = set(roles)
    scores = {}
    for ttype, sig in TABLE_SIGNATURES.items():
        scores[ttype] = len(sig & roleset)
    # берём тип с максимальным совпадением сигнатуры (и хотя бы 1 попадание)
    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        return None
    # спец-случай: investments и storage оба имеют capex -> уточняем
    if best == "investments" and "loss_rate" in roleset:
        return "storage"
    # constraints перебивает demand если есть metric+operator (period ~ year)
    if "metric" in roleset and "operator" in roleset and "value" in roleset:
        return "constraints"
    return best


# ---------------------------------------------------------------------------
# чтение файла
# ---------------------------------------------------------------------------

def read_table(content: bytes, filename: str) -> pd.DataFrame:
    """Прочитать CSV или XLSX в DataFrame. Для xlsx берём первый непустой лист."""
    name = (filename or "").lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        xls = pd.ExcelFile(io.BytesIO(content))
        # выбираем лист с наибольшим числом непустых ячеек
        best_df = None
        best_cells = -1
        for sheet in xls.sheet_names:
            df = xls.parse(sheet)
            cells = int(df.notna().sum().sum())
            if cells > best_cells:
                best_cells = cells
                best_df = df
        return best_df if best_df is not None else pd.DataFrame()
    else:
        # CSV: пробуем определить разделитель (запятая/точка с запятой/таб)
        text = content.decode("utf-8-sig", errors="replace")
        sep = _sniff_sep(text)
        return pd.read_csv(io.StringIO(text), sep=sep)


def _sniff_sep(text: str) -> str:
    first = text.splitlines()[0] if text.splitlines() else ""
    counts = {",": first.count(","), ";": first.count(";"), "\t": first.count("\t")}
    sep = max(counts, key=lambda k: counts[k])
    return sep if counts[sep] > 0 else ","


# ---------------------------------------------------------------------------
# превью и маппинг
# ---------------------------------------------------------------------------

@dataclass
class ColumnMapping:
    source: str          # исходный заголовок
    role: Optional[str]  # угаданная роль (или None)
    samples: List[Any] = field(default_factory=list)


@dataclass
class ImportPreview:
    table_type: Optional[str]
    columns: List[ColumnMapping]
    row_count: int
    sheet_note: str = ""

    def mapping_dict(self) -> Dict[str, str]:
        """role -> source header (только распознанные)."""
        out = {}
        for c in self.columns:
            if c.role and c.role not in out:
                out[c.role] = c.source
        return out


def build_preview(content: bytes, filename: str) -> ImportPreview:
    df = read_table(content, filename)
    cols = []
    roles = []
    for src in df.columns:
        role = guess_role(src)
        roles.append(role)
        samples = [x for x in df[src].head(3).tolist()]
        cols.append(ColumnMapping(source=str(src), role=role, samples=samples))
    ttype = detect_table_type([r for r in roles if r])
    return ImportPreview(table_type=ttype, columns=cols, row_count=len(df))


# ---------------------------------------------------------------------------
# парсинг reliability_profile (специфика каналов)
# ---------------------------------------------------------------------------

def parse_reliability(raw: Any) -> Dict[str, float]:
    """Разобрать профиль надёжности в наш формат {first_year|default|<год>: v}.

    Поддерживаем варианты:
      'constant:0.96'                  -> {default: 0.96}
      'first_operating_year:0.88;later:0.94' -> {first_year:0.88, default:0.94}
      '2038:0.78;2039:0.90;2040:0.93'  -> {2038:.., ...}
      '0.96'                           -> {default: 0.96}
    """
    if raw is None:
        return {"default": 1.0}
    s = str(raw).strip()
    if not s:
        return {"default": 1.0}
    # просто число
    try:
        return {"default": float(s)}
    except ValueError:
        pass
    out: Dict[str, float] = {}
    for part in re.split(r"[;,]", s):
        part = part.strip()
        if not part or ":" not in part:
            continue
        key, val = part.split(":", 1)
        key = key.strip().lower()
        try:
            v = float(val.strip())
        except ValueError:
            continue
        if key in ("constant", "default", "all"):
            out["default"] = v
        elif key in ("first_operating_year", "first_year", "first"):
            out["first_year"] = v
        elif key in ("later", "after", "rest"):
            out["default"] = v
        elif re.fullmatch(r"\d{4}", key):
            out[key] = v
    return out or {"default": 1.0}


def _to_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return default
        return float(str(x).replace(",", ".").strip())
    except (ValueError, TypeError):
        return default


def _to_int_or_none(x: Any) -> Optional[int]:
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        return int(float(x))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# сборка кусков CaseData по подтверждённому маппингу
# ---------------------------------------------------------------------------
# mapping: role -> исходный заголовок колонки. Строим list[dict] под наши
# pydantic-модели (loader потом соберёт CaseData). Возвращаем "сырые" dict'ы,
# чтобы фронт мог показать и при желании доредактировать перед применением.

def _col(row, mapping, role, default=None):
    src = mapping.get(role)
    if src is None:
        return default
    return row.get(src, default)


def build_demand(df: "pd.DataFrame", mapping: Dict[str, str]) -> dict:
    """demand-таблица -> структура demand для CaseData."""
    years = {}
    for _, row in df.iterrows():
        y = _to_int_or_none(_col(row, mapping, "year"))
        if y is None:
            continue
        base = _to_float(_col(row, mapping, "base_total"))
        crit = _to_float(_col(row, mapping, "critical"))
        low = _to_float(_col(row, mapping, "low_total"), base)
        high = _to_float(_col(row, mapping, "high_total"), base)
        years[y] = {
            "base_total": base, "critical": crit,
            "low_total": low, "high_total": high,
        }
    return {"status": "case", "years": years}


def build_channels(df: "pd.DataFrame", mapping: Dict[str, str]) -> List[dict]:
    """supply_sources -> список каналов."""
    out = []
    for i, (_, row) in enumerate(df.iterrows()):
        cid = _col(row, mapping, "id")
        cid = str(cid).strip() if cid is not None else chr(ord("A") + i)
        # lead time: берём min, если есть; единицы недели -> в месяцы
        lead = _to_float(_col(row, mapping, "lead_time_months")
                         or _col(row, mapping, "lead_time_min"), 0)
        unit = _col(row, mapping, "lead_time_unit")
        if unit and "week" in str(unit).lower():
            lead = round(lead / 4.0, 2)  # недели -> месяцы (грубо)
        rel = parse_reliability(_col(row, mapping, "reliability"))
        requires = (str(_col(row, mapping, "requires")).strip()
                    if _col(row, mapping, "requires") else None)
        available_from = _to_int_or_none(_col(row, mapping, "available_from"))
        # если в файле нет колонки requires/available_from - подставим типовую
        # привязку для известных каналов (C через опцион, D через ISRU-пилот).
        # это "мягкая" эвристика формата-ориентира; при явных колонках она не
        # срабатывает.
        nm = norm(_col(row, mapping, "name", "")) + " " + norm(cid)
        if requires is None:
            if "new" in nm or cid.upper() == "C":
                requires = "earth_new_option"
            elif "isru" in nm or "lunar" in nm or cid.upper() == "D":
                requires = "isru_pilot"
        out.append({
            "id": cid,
            "name": str(_col(row, mapping, "name", cid)),
            "capacity": _to_float(_col(row, mapping, "capacity")),
            "var_cost": _to_float(_col(row, mapping, "var_cost")),
            "reservation_rate": _to_float(_col(row, mapping, "reservation_rate")),
            "take_or_pay": _to_float(_col(row, mapping, "take_or_pay")),
            "lead_time_months": lead,
            "reliability": rel,
            "available_from": available_from,
            "requires": requires,
        })
    return out


def build_storage(df: "pd.DataFrame", mapping: Dict[str, str]) -> dict:
    """storage_options -> {base, zbo_upgrade}. Различаем по id/name/capex."""
    base = None
    zbo = None
    for _, row in df.iterrows():
        raw_cost = _col(row, mapping, "storage_cost")
        mode = {
            "capacity": _to_float(_col(row, mapping, "capacity")),
            "loss_rate": _to_float(_col(row, mapping, "loss_rate")),
            "storage_cost": _to_float(raw_cost) if raw_cost is not None else None,
            "capex": _to_float(_col(row, mapping, "capex")),
            "extra_opex": _to_float(_col(row, mapping, "extra_opex")),
        }
        ident = str(_col(row, mapping, "id") or _col(row, mapping, "name") or "").lower()
        # базовое хранилище - с нулевым capex или id вроде base
        if "zbo" in ident or mode["capex"] > 0:
            zbo = mode
        else:
            base = mode
    if base is None:
        base = {"capacity": 70, "loss_rate": 0.045, "storage_cost": 0.72, "capex": 0, "extra_opex": 0}
    return {"status": "case", "base": base, "zbo_upgrade": zbo}


def build_investments(df: "pd.DataFrame", mapping: Dict[str, str]) -> List[dict]:
    """investment_options -> список инвестиций."""
    out = []
    for _, row in df.iterrows():
        iid = _col(row, mapping, "id")
        if iid is None:
            continue
        total = _to_float(_col(row, mapping, "capex"))
        fee = _to_float(_col(row, mapping, "option_fee"))
        exercise = _to_float(_col(row, mapping, "exercise_cost"))
        if total == 0 and (fee or exercise):
            total = fee + exercise
        out.append({
            "id": _canon_investment_id(str(iid)),
            "name": str(_col(row, mapping, "name", iid)),
            "capex": total,
            "extra_opex": _to_float(_col(row, mapping, "extra_opex")),
        })
    return out


# алиасы id инвестиций -> канонические id, которые ждёт модель (channels.requires,
# планы). Разные источники называют их по-разному (EARTH_NEW, earth-new-option...).
_INV_ID_ALIASES = {
    "earth_new": "earth_new_option",
    "earthnew": "earth_new_option",
    "earth_new_option": "earth_new_option",
    "lunar_isru": "isru_pilot",
    "isru": "isru_pilot",
    "isru_pilot": "isru_pilot",
    "lunar_isru_pilot": "isru_pilot",
    "zbo": "zbo_upgrade",
    "zbo_modernization": "zbo_upgrade",
    "zbo_upgrade": "zbo_upgrade",
}


def _canon_investment_id(raw: str) -> str:
    key = norm(raw).replace(" ", "_")
    return _INV_ID_ALIASES.get(key, key)


def build_from_preview(df: "pd.DataFrame", table_type: str,
                       mapping: Dict[str, str]) -> dict:
    """Универсальная точка: по типу таблицы собрать соответствующий кусок.

    Возвращает {'kind': <type>, 'data': <...>} для фронта/применения.
    """
    if table_type == "demand":
        return {"kind": "demand", "data": build_demand(df, mapping)}
    elif table_type == "channels":
        return {"kind": "channels", "data": build_channels(df, mapping)}
    elif table_type == "storage":
        return {"kind": "storage", "data": build_storage(df, mapping)}
    elif table_type == "investments":
        return {"kind": "investments", "data": build_investments(df, mapping)}
    elif table_type == "constraints":
        # ограничения не перестраиваем автоматически (риск сломать проверки),
        # просто отдаём распознанные строки для показа
        return {"kind": "constraints", "data": df.to_dict(orient="records")}
    return {"kind": "unknown", "data": []}
