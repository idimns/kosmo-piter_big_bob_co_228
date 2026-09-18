"""Тесты гибкого импорта CSV/XLSX."""
import io
import pytest
import pandas as pd
from pathlib import Path

from fuelcontour.io import importer

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"


# --- нормализация и угадывание ролей ---

def test_norm():
    assert importer.norm("Capacity (t/year)") == "capacity t year"
    assert importer.norm("Take-Or-Pay") == "take or pay"
    assert importer.norm("Цена, млн/т") == "цена млн т"


def test_guess_role_basic():
    assert importer.guess_role("capacity_t_per_year") == "capacity"
    assert importer.guess_role("Мощность (т/год)") == "capacity"
    assert importer.guess_role("take_or_pay_share") == "take_or_pay"
    assert importer.guess_role("base_critical_t") == "critical"


def test_guess_role_specificity():
    # 'base critical' должен выиграть у общего 'critical'->critical, и не спутать с base_total
    assert importer.guess_role("base_total_t") == "base_total"
    assert importer.guess_role("base_critical_t") == "critical"


# --- reliability profile ---

def test_parse_reliability_variants():
    assert importer.parse_reliability("constant:0.96") == {"default": 0.96}
    assert importer.parse_reliability("0.985") == {"default": 0.985}
    r = importer.parse_reliability("first_operating_year:0.88;later:0.94")
    assert r == {"first_year": 0.88, "default": 0.94}
    r2 = importer.parse_reliability("2038:0.78;2039:0.90;2040:0.93")
    assert r2 == {"2038": 0.78, "2039": 0.9, "2040": 0.93}


# --- определение типа таблицы ---

def test_detect_types_on_reference():
    cases = {
        "ref_demand.csv": "demand",
        "ref_supply_sources.csv": "channels",
        "ref_storage_options.csv": "storage",
        "ref_investment_options.csv": "investments",
        "ref_constraints.csv": "constraints",
    }
    for fname, expected in cases.items():
        content = (FIX / fname).read_bytes()
        prev = importer.build_preview(content, fname)
        assert prev.table_type == expected, f"{fname}: got {prev.table_type}"


# --- сборка каналов из референса ---

def test_build_channels_reference():
    content = (FIX / "ref_supply_sources.csv").read_bytes()
    prev = importer.build_preview(content, "ref_supply_sources.csv")
    df = importer.read_table(content, "ref_supply_sources.csv")
    built = importer.build_from_preview(df, prev.table_type, prev.mapping_dict())
    chans = {c["id"]: c for c in built["data"]}
    assert chans["A"]["capacity"] == 190.0
    assert chans["A"]["var_cost"] == 6.2
    assert chans["A"]["take_or_pay"] == 0.70
    # Emergency: 6 недель -> 1.5 месяца
    assert abs(chans["E"]["lead_time_months"] - 1.5) < 1e-6
    # надёжность C - профиль first_year
    assert chans["C"]["reliability"] == {"first_year": 0.88, "default": 0.94}
    # гейты выведены
    assert chans["C"]["requires"] == "earth_new_option"
    assert chans["D"]["requires"] == "isru_pilot"


def test_build_investments_total_capex():
    """total_capex должен победить exercise_cost для роли capex (Earth-New=360)."""
    content = (FIX / "ref_investment_options.csv").read_bytes()
    prev = importer.build_preview(content, "ref_investment_options.csv")
    df = importer.read_table(content, "ref_investment_options.csv")
    built = importer.build_from_preview(df, prev.table_type, prev.mapping_dict())
    inv = {i["id"]: i for i in built["data"]}
    assert inv["earth_new_option"]["capex"] == 360.0
    assert inv["isru_pilot"]["capex"] == 1250.0


# --- messy headers (русские, лишние колонки, ; разделитель) ---

def test_messy_russian_headers():
    csv = ("Канал;Мощность (т/год);Цена, млн/т;Take-Or-Pay;Заметка\n"
           "Earth-Core;190;6.2;0.7;основной\n"
           "Flex;110;8.9;0;гибкий\n")
    content = csv.encode("utf-8")
    prev = importer.build_preview(content, "messy.csv")
    assert prev.table_type == "channels"
    df = importer.read_table(content, "messy.csv")
    built = importer.build_from_preview(df, prev.table_type, prev.mapping_dict())
    assert len(built["data"]) == 2
    assert built["data"][0]["capacity"] == 190.0
    assert built["data"][0]["var_cost"] == 6.2


def test_xlsx_roundtrip():
    """Импорт из XLSX (создаём на лету) - выбирается лист с данными."""
    df = pd.DataFrame({
        "year": [2035, 2036],
        "base total": [100, 140],
        "critical": [80, 105],
    })
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        pd.DataFrame().to_excel(xw, sheet_name="empty", index=False)
        df.to_excel(xw, sheet_name="data", index=False)
    content = buf.getvalue()
    prev = importer.build_preview(content, "demand.xlsx")
    assert prev.table_type == "demand"
    assert prev.row_count == 2
    df2 = importer.read_table(content, "demand.xlsx")
    built = importer.build_from_preview(df2, prev.table_type, prev.mapping_dict())
    assert built["data"]["years"][2035]["base_total"] == 100


def test_semicolon_separator_sniff():
    csv = "year;base_total;critical\n2035;100;80\n"
    df = importer.read_table(csv.encode("utf-8"), "d.csv")
    assert list(df.columns) == ["year", "base_total", "critical"]
    assert len(df) == 1


def test_manual_mapping_override():
    """Ручной маппинг: колонка с непонятным именем -> нужная роль."""
    csv = "период;чего_то;X\n2035;100;80\n2036;140;105\n"
    content = csv.encode("utf-8")
    df = importer.read_table(content, "x.csv")
    # авто не распознает 'чего_то' как base_total; зададим вручную
    mapping = {"year": "период", "base_total": "чего_то", "critical": "X"}
    built = importer.build_from_preview(df, "demand", mapping)
    assert built["data"]["years"][2035]["base_total"] == 100.0
    assert built["data"]["years"][2036]["critical"] == 105.0
