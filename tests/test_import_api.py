"""Тесты API импорта данных."""
import json
import pytest
from pathlib import Path

from fastapi.testclient import TestClient
from fuelcontour.api.app import create_app

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"


@pytest.fixture
def client():
    return TestClient(create_app())


def _upload(client, fname):
    content = (FIX / fname).read_bytes()
    return client.post("/api/import/preview",
                       files={"file": (fname.replace("ref_", ""), content, "text/csv")})


def test_preview_channels(client):
    r = _upload(client, "ref_supply_sources.csv")
    assert r.status_code == 200
    j = r.json()
    assert j["table_type"] == "channels"
    assert j["row_count"] == 5
    assert j["preview"]["kind"] == "channels"


def test_preview_bad_file(client):
    r = client.post("/api/import/preview",
                    files={"file": ("junk.csv", b"\x00\x01 not a table", "text/csv")})
    # либо 422, либо распознан как unknown (table_type None) - не должно падать 500
    assert r.status_code in (200, 422)


def test_apply_channels_updates_case(client):
    prev = _upload(client, "ref_supply_sources.csv").json()
    r = client.post("/api/import/apply", json={"pieces": [prev["preview"]]})
    assert r.status_code == 200
    # мердж по id: 5 каналов обновлено
    assert any("channels" in a and "5" in a for a in r.json()["applied"])
    # кейс обновился
    case = client.get("/api/case").json()
    assert len(case["channels"]) == 5


def test_partial_channel_import_keeps_others(client):
    """Частичный импорт (только A) не должен удалять C/D/E - мердж по id."""
    client.post("/api/import/reset")
    csv = ("source_id,name,capacity_t_per_year,variable_cost_mln_per_t,"
           "reservation_rate_mln_per_t_year_capacity,take_or_pay_share,"
           "lead_time_min_value,lead_time_unit,reliability_profile,available_from_year\n"
           "A,Earth-Core,190,99.9,0.45,0.70,12,month,constant:0.96,2035\n")
    prev = client.post("/api/import/preview",
                       files={"file": ("one.csv", csv.encode(), "text/csv")}).json()
    client.post("/api/import/apply", json={"pieces": [prev["preview"]]})
    case = client.get("/api/case").json()
    ids = [c["id"] for c in case["channels"]]
    # все 5 каналов на месте, A обновлён
    assert ids == ["A", "B", "C", "D", "E"]
    a = next(c for c in case["channels"] if c["id"] == "A")
    assert a["var_cost"] == 99.9
    client.post("/api/import/reset")


def test_plan_with_unknown_channel_gives_422(client):
    """План со ссылкой на несуществующий канал -> 422, а не 500."""
    client.post("/api/import/reset")
    bad_plan = {"initial_stock": 0, "plan": {"2035": [{"channel_id": "Z", "ordered": 10}]}}
    r = client.post("/api/plan/evaluate", json={"decision": bad_plan, "scenario_id": "standard"})
    assert r.status_code == 422
    assert "неизвестные каналы" in r.json()["detail"]


def test_full_import_reproduces_result(client):
    """Импорт всех референсных файлов -> тот же расчёт, что на исходных данных."""
    pieces = []
    for fname in ["ref_demand.csv", "ref_supply_sources.csv",
                  "ref_storage_options.csv", "ref_investment_options.csv"]:
        j = _upload(client, fname).json()
        if j.get("preview"):
            pieces.append(j["preview"])
    client.post("/api/import/apply", json={"pieces": pieces})

    plan = json.loads((ROOT / "results" / "plan_standard.json").read_text())
    d = client.post("/api/plan/evaluate", json={"decision": plan, "scenario_id": "standard"}).json()
    # исходный результат = 11381.2
    assert abs(d["economics"]["total_cost"] - 11381.2) < 0.5


def test_manual_remap_via_api(client):
    """Файл с непонятными заголовками + ручной маппинг через override."""
    csv = "col1,col2,col3\n2035,100,80\n2036,140,105\n"
    override = json.dumps({"year": "col1", "base_total": "col2", "critical": "col3"})
    r = client.post(
        "/api/import/preview",
        files={"file": ("weird.csv", csv.encode(), "text/csv")},
        data={"mapping_override": override, "table_type_override": "demand"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["table_type"] == "demand"
    assert j["preview"]["data"]["years"]["2035"]["base_total"] == 100.0


def test_reset_restores_original(client):
    # импортируем, потом сбрасываем
    prev = _upload(client, "ref_supply_sources.csv").json()
    client.post("/api/import/apply", json={"pieces": [prev["preview"]]})
    r = client.post("/api/import/reset")
    assert r.status_code == 200
    # после сброса кейс снова исходный (5 каналов из yaml)
    case = client.get("/api/case").json()
    assert len(case["channels"]) == 5
    assert case["channels"][0]["id"] == "A"
