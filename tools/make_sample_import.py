"""Генератор тестового файла для импорта: один XLSX меняет ВСЕ данные кейса.

Запуск: python tools/make_sample_import.py
Создаёт data/sample_import_full.xlsx с 4 листами (спрос, каналы, хранилище,
инвестиции), значения намеренно СИЛЬНО отличаются от исходного кейса, чтобы
после импорта было видно изменение во всех числах и графиках.

Заголовки колонок нарочно в "человеческом" стиле (с единицами, разный регистр) -
показать, что фаззи-импорт справляется с нестрогой структурой.
"""
import pandas as pd
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "sample_import_full.xlsx"

# --- спрос: резко выше исходного (исходный 100..390) ---
demand = pd.DataFrame({
    "Год": [2035, 2036, 2037, 2038, 2039, 2040],
    "Общий спрос (т/год)": [200, 260, 330, 410, 500, 600],
    "Критический (т/год)": [160, 200, 250, 300, 360, 430],
    "Низкий": [160, 210, 265, 330, 400, 480],
    "Высокий": [220, 290, 365, 450, 550, 660],
})

# --- каналы: другие цены/мощности (исходный A=6.2/190, B=8.9/110 ...) ---
channels = pd.DataFrame({
    "source_id": ["A", "B", "C", "D", "E"],
    "Название": ["Earth-Core", "Earth-Flex", "Earth-New", "Lunar-ISRU", "Emergency"],
    "Мощность (т/год)": [230, 140, 160, 180, 100],
    "Цена, млн/т": [5.5, 9.5, 6.8, 2.4, 15.0],
    "Ставка резерва": [0.40, 0.18, 0.28, 0.00, 0.40],
    "take-or-pay": [0.65, 0.00, 0.55, 0.00, 0.00],
    "lead_time_min_value": [12, 4, 18, 1, 6],
    "lead_time_unit": ["month", "month", "month", "month", "week"],
    "reliability_profile": ["constant:0.97", "constant:0.99",
                            "first_operating_year:0.90;later:0.95",
                            "2038:0.80;2039:0.92;2040:0.95", "constant:0.995"],
    "available_from_year": [2035, 2035, "", 2038, 2035],
})

# --- хранилище: другая ёмкость/потери ---
storage = pd.DataFrame({
    "storage_id": ["BASE", "ZBO"],
    "Название": ["Base storage", "ZBO modernization"],
    "Ёмкость (т)": [90, 160],
    "Потери от оборота": [0.050, 0.010],
    "Стоимость хранения (млн/т-год)": [0.68, 0.68],
    "CAPEX (млн)": [0, 220],
    "fixed_opex_mln_per_year": [0, 15],
})

# --- инвестиции: другие CAPEX ---
investments = pd.DataFrame({
    "investment_id": ["EARTH_NEW", "LUNAR_ISRU", "ZBO"],
    "Название": ["Earth-New option", "Lunar-ISRU pilot", "ZBO modernization"],
    "option_fee_mln": [100, 0, 0],
    "exercise_cost_mln": [300, 1400, 220],
    "total_capex_mln": [400, 1400, 220],
    "fixed_opex_mln_per_year": [0, 80, 15],
})

with pd.ExcelWriter(OUT, engine="openpyxl") as xw:
    demand.to_excel(xw, sheet_name="demand", index=False)
    channels.to_excel(xw, sheet_name="supply_sources", index=False)
    storage.to_excel(xw, sheet_name="storage", index=False)
    investments.to_excel(xw, sheet_name="investments", index=False)

print(f"created: {OUT}")
