"""Загрузка данных кейса, сценариев и планов из YAML/JSON.

Данные кейса - YAML (человекочитаемо, версионируется).
Планы пользователя - JSON (results/).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import yaml

from ..model.entities import (
    CaseData, Demand, Channel, Storage, StorageMode, Investment,
    Constraints, ScenarioDef, Decision,
)


def load_case(path: str | Path) -> CaseData:
    """Собрать CaseData из data/case.yaml."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))

    demand = Demand(**raw["demand"])
    channels = [Channel(**c) for c in raw["channels"]["items"]]

    st = raw["storage"]
    storage = Storage(
        base=StorageMode(**st["base"]),
        zbo_upgrade=StorageMode(**st["zbo_upgrade"]) if st.get("zbo_upgrade") else None,
    )

    investments = [Investment(**i) for i in raw["investments"]["items"]]
    constraints = Constraints(**raw["constraints"])

    return CaseData(
        meta=raw.get("meta", {}),
        demand=demand,
        channels=channels,
        storage=storage,
        investments=investments,
        constraints=constraints,
    )


def load_scenario(path: str | Path) -> ScenarioDef:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return ScenarioDef(**raw)


def load_scenarios(configs_dir: str | Path) -> Dict[str, ScenarioDef]:
    """Загрузить все сценарии из configs/*.yaml."""
    d = Path(configs_dir)
    out = {}
    for f in sorted(d.glob("*.yaml")):
        scn = load_scenario(f)
        out[scn.id] = scn
    return out


def load_decision(path: str | Path) -> Decision:
    """Загрузить план (решение) из JSON."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    # ключи-годы в JSON - строки, приводим к int
    if "plan" in raw and isinstance(raw["plan"], dict):
        raw["plan"] = {int(k): v for k, v in raw["plan"].items()}
    return Decision(**raw)


def save_decision(decision: Decision, path: str | Path) -> None:
    """Сохранить план в JSON (для повторного открытия, с.8)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = decision.model_dump()
    # year-ключи в строки для валидного json
    if "plan" in data:
        data["plan"] = {str(k): v for k, v in data["plan"].items()}
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
