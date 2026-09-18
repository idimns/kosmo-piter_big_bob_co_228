"""Тесты API - проверяем эндпоинты и совпадение чисел с ядром."""
import json
import pytest
from pathlib import Path

from fastapi.testclient import TestClient

from fuelcontour.api.app import create_app

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.fixture
def plan():
    return json.loads((ROOT / "results" / "plan_standard.json").read_text(encoding="utf-8"))


def test_get_case(client):
    r = client.get("/api/case")
    assert r.status_code == 200
    assert len(r.json()["channels"]) == 5


def test_get_scenarios(client):
    r = client.get("/api/scenarios")
    assert r.status_code == 200
    ids = [s["id"] for s in r.json()]
    assert "standard" in ids and "stress" in ids


def test_evaluate_matches_core(client, plan):
    """API отдаёт те же числа, что и ядро (Правило 3)."""
    r = client.post("/api/plan/evaluate", json={"decision": plan, "scenario_id": "standard"})
    assert r.status_code == 200
    d = r.json()
    assert d["feasible"] is True
    # число из ядра, зафиксировано golden-прогоном
    assert abs(d["economics"]["total_cost"] - 11381.2) < 0.5


def test_evaluate_bad_input_422(client):
    """Отрицательный заказ -> понятная ошибка 422 (критерий №19)."""
    bad = {"plan": {"2035": [{"channel_id": "A", "ordered": -5}]}}
    r = client.post("/api/plan/evaluate", json={"decision": bad, "scenario_id": "standard"})
    assert r.status_code == 422


def test_unknown_scenario_404(client, plan):
    r = client.post("/api/plan/evaluate", json={"decision": plan, "scenario_id": "nope"})
    assert r.status_code == 404


def test_compare_endpoint(client, plan):
    r = client.post("/api/scenario/compare", json={"decision": plan})
    assert r.status_code == 200
    d = r.json()
    assert "standard" in d and "stress" in d and "diff" in d


def test_export_csv(client, plan):
    r = client.post("/api/export", json={"decision": plan, "scenario_id": "standard", "fmt": "csv"})
    assert r.status_code == 200
    assert len(r.content) > 0


def test_geopolitical_endpoint(client, plan):
    body = {
        "decision": plan,
        "scenario_id": "standard",
        "event": {
            "event_id": "t", "description": "test shock",
            "affected_channels": ["A"], "direction": "increase", "magnitude": 0.25,
        },
    }
    r = client.post("/api/geopolitical/apply", json=body)
    assert r.status_code == 200
    d = r.json()
    assert d["cost_delta"] > 0
    assert "causal_chain" in d


def test_save_and_load_plan(client, plan, tmp_path):
    # сохраняем под тестовым именем
    r = client.post("/api/plans/_test_plan", json={"decision": plan, "scenario_id": "standard"})
    assert r.status_code == 200
    # загружаем обратно
    r2 = client.get("/api/plans/_test_plan")
    assert r2.status_code == 200
    # чистим
    fp = ROOT / "results" / "_test_plan.json"
    if fp.exists():
        fp.unlink()
