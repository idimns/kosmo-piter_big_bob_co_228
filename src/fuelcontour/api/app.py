"""FastAPI-приложение - тонкий слой поверх расчётного ядра.

Эндпоинты:
  GET  /api/case                  данные кейса
  GET  /api/scenarios             список сценариев
  POST /api/plan/evaluate         {decision, scenario_id} -> Result
  POST /api/scenario/compare      {decision} -> standard + stress + diff
  GET  /api/plans                 список сохранённых планов
  GET  /api/plans/{name}          загрузить план
  POST /api/plans/{name}          сохранить план
  POST /api/export                {decision, scenario_id, fmt} -> файл
  POST /api/geopolitical/apply    {decision, scenario_id, event} -> до/после

Валидация ввода -> понятное сообщение. Ядро не знает про HTTP.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..io.loader import load_case, load_scenarios
from ..model.entities import Decision, ScenarioDef, CaseData, Demand, Channel, Storage, StorageMode, Investment
from ..engine.pipeline import evaluate_plan, compare
from ..engine.geopolitical import GeoEvent, run_geopolitical
from ..io.export import export_xlsx, result_to_csv_string
from ..io import importer
from .serializers import result_to_dict, case_to_dict

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data" / "case.yaml"
CONFIGS = ROOT / "configs"
RESULTS = ROOT / "results"


# --- тела запросов -----------------------------------------------------------

class EvaluateRequest(BaseModel):
    decision: dict
    scenario_id: str = "standard"


class CompareRequest(BaseModel):
    decision: dict


class ExportRequest(BaseModel):
    decision: dict
    scenario_id: str = "standard"
    fmt: str = "xlsx"           # xlsx | csv


class GeoEventBody(BaseModel):
    event_id: str = "geo_event"
    description: str = ""
    affected_channels: list[str] = []
    price_component: str = "aggregate"
    direction: str = "increase"
    magnitude: float = 0.0
    from_year: Optional[int] = None
    to_year: Optional[int] = None
    basis: str = ""


class GeoRequest(BaseModel):
    decision: dict
    scenario_id: str = "standard"
    event: GeoEventBody
    combine_with_stress: bool = False


class ImportApplyRequest(BaseModel):
    # применённые куски импорта: список {kind, data} от превью (возможно
    # отредактированных пользователем после ручного маппинга)
    pieces: list[dict]


def _rebuild_case(d: dict) -> CaseData:
    """Собрать CaseData из dict-представления (case_to_dict + правки импорта).

    Терпимо к отсутствующим секциям - берём что есть. Годы-ключи спроса могут
    прийти строками (из JSON) - приводим к int.
    """
    dem = d["demand"]
    years_raw = dem.get("years", {})
    years = {int(k): v for k, v in years_raw.items()}
    demand = Demand(status="case", years=years)

    channels = [Channel(**c) for c in d["channels"]]

    st = d["storage"]
    storage = Storage(
        base=StorageMode(**st["base"]),
        zbo_upgrade=StorageMode(**st["zbo_upgrade"]) if st.get("zbo_upgrade") else None,
    )

    investments = [Investment(**i) for i in d["investments"]]

    # ограничения оставляем как в текущем кейсе (импортом не трогаем)
    from ..model.entities import Constraints
    constraints = Constraints(**d["constraints"]) if isinstance(d.get("constraints"), dict) else Constraints()

    return CaseData(
        meta=d.get("meta", {}),
        demand=demand,
        channels=channels,
        storage=storage,
        investments=investments,
        constraints=constraints,
    )


# --- фабрика приложения ------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(title="Топливный космоконтур 2035", version="0.1.0")

    # CORS для дев-режима (фронт на другом порту)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # загружаем кейс и сценарии один раз при старте.
    # case держим в изменяемом контейнере - импорт может его заменить.
    state = {"case": load_case(DATA)}
    scenarios = load_scenarios(CONFIGS)

    def cur_case():
        return state["case"]

    def _parse_decision(raw: dict) -> Decision:
        try:
            # year-ключи в plan могут прийти строками
            if "plan" in raw and isinstance(raw["plan"], dict):
                raw = {**raw, "plan": {int(k): v for k, v in raw["plan"].items()}}
            return Decision(**raw)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Некорректный план: {e}")

    def _get_scenario(sid: str) -> ScenarioDef:
        if sid not in scenarios:
            raise HTTPException(
                status_code=404,
                detail=f"Нет сценария '{sid}'. Доступны: {list(scenarios)}",
            )
        return scenarios[sid]

    def _validate_plan(decision: Decision):
        """План не должен ссылаться на каналы/инвестиции, которых нет в кейсе.
        Иначе движок упадёт - отдаём понятную 422 вместо 500."""
        known_ch = {c.id for c in cur_case().channels}
        known_inv = {i.id for i in cur_case().investments}
        bad_ch = set()
        for year, items in decision.plan.items():
            for cd in items:
                if cd.channel_id not in known_ch:
                    bad_ch.add(cd.channel_id)
        bad_inv = {i for i in decision.investments if i not in known_inv}
        if bad_ch:
            raise HTTPException(
                status_code=422,
                detail=f"План ссылается на неизвестные каналы: {sorted(bad_ch)}. "
                       f"Доступны: {sorted(known_ch)}",
            )
        if bad_inv:
            raise HTTPException(
                status_code=422,
                detail=f"План ссылается на неизвестные инвестиции: {sorted(bad_inv)}. "
                       f"Доступны: {sorted(known_inv)}",
            )

    @app.get("/api/case")
    def get_case():
        return case_to_dict(cur_case())

    @app.get("/api/scenarios")
    def get_scenarios():
        return [
            {"id": s.id, "name": s.name, "description": s.description}
            for s in scenarios.values()
        ]

    @app.post("/api/plan/evaluate")
    def evaluate(req: EvaluateRequest):
        decision = _parse_decision(req.decision)
        scn = _get_scenario(req.scenario_id)
        _validate_plan(decision)
        res = evaluate_plan(cur_case(), decision, scn)
        return result_to_dict(res)

    @app.post("/api/scenario/compare")
    def scenario_compare(req: CompareRequest):
        decision = _parse_decision(req.decision)
        _validate_plan(decision)
        std = evaluate_plan(cur_case(), decision, _get_scenario("standard"))
        strs = evaluate_plan(cur_case(), decision, _get_scenario("stress"))
        return {
            "standard": result_to_dict(std),
            "stress": result_to_dict(strs),
            "diff": compare(std, strs),
        }

    @app.get("/api/plans")
    def list_plans():
        RESULTS.mkdir(exist_ok=True)
        return [p.stem for p in RESULTS.glob("*.json")]

    @app.get("/api/plans/{name}")
    def get_plan(name: str):
        fp = RESULTS / f"{name}.json"
        if not fp.exists():
            raise HTTPException(status_code=404, detail=f"План '{name}' не найден")
        return json.loads(fp.read_text(encoding="utf-8"))

    @app.post("/api/plans/{name}")
    def save_plan(name: str, req: EvaluateRequest):
        # валидируем перед сохранением
        _parse_decision(req.decision)
        RESULTS.mkdir(exist_ok=True)
        fp = RESULTS / f"{name}.json"
        payload = {**req.decision, "scenario_id": req.scenario_id}
        fp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"saved": name, "path": str(fp.name)}

    @app.post("/api/export")
    def export(req: ExportRequest):
        decision = _parse_decision(req.decision)
        scn = _get_scenario(req.scenario_id)
        _validate_plan(decision)
        res = evaluate_plan(cur_case(), decision, scn)

        if req.fmt == "csv":
            content = result_to_csv_string(res)
            return StreamingResponse(
                io.BytesIO(content.encode("utf-8-sig")),
                media_type="text/csv",
                headers={"Content-Disposition":
                         f'attachment; filename="{req.scenario_id}_plan.csv"'},
            )
        else:
            RESULTS.mkdir(exist_ok=True)
            fp = RESULTS / f"export_{req.scenario_id}.xlsx"
            export_xlsx(res, fp)
            return FileResponse(
                fp,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                filename=f"{req.scenario_id}_export.xlsx",
            )

    @app.post("/api/geopolitical/apply")
    def geopolitical(req: GeoRequest):
        decision = _parse_decision(req.decision)
        scn = _get_scenario(req.scenario_id)
        _validate_plan(decision)
        ev = GeoEvent(
            event_id=req.event.event_id,
            description=req.event.description,
            affected_channels=req.event.affected_channels,
            price_component=req.event.price_component,
            direction=req.event.direction,
            magnitude=req.event.magnitude,
            from_year=req.event.from_year,
            to_year=req.event.to_year,
            basis=req.event.basis,
        )
        geo = run_geopolitical(cur_case(), decision, scn, ev, req.combine_with_stress)
        return {
            "causal_chain": geo.causal_chain,
            "price_before": geo.price_before,
            "price_after": geo.price_after,
            "cost_delta": geo.cost_delta,
            "before": result_to_dict(geo.before),
            "after": result_to_dict(geo.after),
        }

    # --- оптимизация, чувствительность, монте-карло --------------------------

    def _decision_to_dict(dec) -> dict:
        return {
            "scenario_id": dec.scenario_id,
            "initial_stock": dec.initial_stock,
            "use_zbo": dec.use_zbo,
            "investments": dec.investments,
            "plan": {str(y): [{"channel_id": c.channel_id,
                               "reserved_capacity": c.reserved_capacity,
                               "ordered": c.ordered} for c in items]
                     for y, items in dec.plan.items()},
        }

    @app.post("/api/optimize")
    def api_optimize(req: dict):
        """MILP-оптимизация плана с проверкой движком."""
        from ..engine.optimizer import optimize_and_verify
        scenario_id = req.get("scenario_id", "standard")
        scn = _get_scenario(scenario_id)
        res = optimize_and_verify(cur_case(), scn, time_limit=req.get("time_limit", 20))
        if not res["feasible"]:
            raise HTTPException(status_code=422, detail=f"Оптимум не найден: {res['status']}")
        return {
            "status": res["status"],
            "iterations": res["iterations"],
            "lower_bound": res["lower_bound"],
            "engine_total": res["engine_total"],
            "engine_discounted": res["engine_discounted"],
            "gap_pct": res["gap_pct"],
            "decision": _decision_to_dict(res["decision"]),
            "result": result_to_dict(res["result"]),
        }

    @app.post("/api/sensitivity")
    def api_sensitivity(req: dict):
        """Торнадо-анализ чувствительности."""
        from ..engine.sensitivity import tornado
        decision = _parse_decision(req["decision"])
        _validate_plan(decision)
        scn = _get_scenario(req.get("scenario_id", "standard"))
        return tornado(cur_case(), decision, scn, delta=req.get("delta", 0.2))

    @app.post("/api/montecarlo")
    def api_montecarlo(req: dict):
        """Монте-Карло оценка рисков (детерминирован по seed)."""
        from ..engine.montecarlo import run_montecarlo
        decision = _parse_decision(req["decision"])
        _validate_plan(decision)
        scn = _get_scenario(req.get("scenario_id", "stress"))
        mc = run_montecarlo(cur_case(), decision, scn,
                            trials=req.get("trials", 2000), seed=req.get("seed", 42))
        return mc.as_dict()

    # --- импорт данных из CSV/XLSX ------------------------------------------

    @app.post("/api/import/preview")
    async def import_preview(
        file: UploadFile = File(...),
        mapping_override: Optional[str] = Form(None),
        table_type_override: Optional[str] = Form(None),
    ):
        """Загрузить файл, вернуть распознанный тип, маппинг колонок и превью.

        Не меняет данные - только показывает, что импортёр понял. Пользователь
        потом подтверждает/правит маппинг и вызывает apply.

        mapping_override - JSON {role: source_header} для ручной правки маппинга.
        table_type_override - если пользователь сам выбрал тип таблицы.
        """
        content = await file.read()
        fname = file.filename or "upload.csv"
        try:
            prev = importer.build_preview(content, fname)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Не удалось прочитать файл: {e}")

        # определяем итоговый тип и маппинг (с учётом ручных правок)
        ttype = table_type_override or prev.table_type
        mapping = prev.mapping_dict()
        if mapping_override:
            try:
                ovr = json.loads(mapping_override)
                # чистим пустые значения, накладываем поверх авто-маппинга
                mapping.update({k: v for k, v in ovr.items() if v})
            except json.JSONDecodeError:
                pass

        # собираем черновой результат, чтобы сразу показать превью применяемого
        built = None
        if ttype:
            try:
                df = importer.read_table(content, fname)
                built = importer.build_from_preview(df, ttype, mapping)
            except Exception:
                built = None

        return {
            "filename": file.filename,
            "table_type": ttype,
            "row_count": prev.row_count,
            "columns": [
                {"source": c.source, "role": c.role,
                 "samples": [str(s) for s in c.samples]}
                for c in prev.columns
            ],
            "known_roles": list(importer.FIELD_SYNONYMS.keys()),
            "table_types": list(importer.TABLE_SIGNATURES.keys()),
            "preview": built,
        }

    @app.post("/api/import/preview-all")
    async def import_preview_all(file: UploadFile = File(...)):
        """Многолистовой импорт: один файл (XLSX с листами или CSV) -> ВСЕ таблицы.

        Возвращает список распознанных кусков (demand/channels/storage/
        investments). Дальше их можно применить одним вызовом apply.
        """
        content = await file.read()
        fname = file.filename or "upload.xlsx"
        try:
            pieces = importer.build_all_pieces(content, fname)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Не удалось прочитать файл: {e}")
        return {
            "filename": file.filename,
            "pieces": pieces,
            "kinds": [p["kind"] for p in pieces],
        }

    @app.post("/api/import/apply")
    def import_apply(req: ImportApplyRequest):
        """Применить импортированные куски к рабочему кейсу.

        Работаем на копии текущего кейса; заменяем только пришедшие секции
        (demand/channels/storage/investments). Возвращаем сводку изменений.
        """
        base = case_to_dict(cur_case())  # текущее как основа
        applied = []

        for piece in req.pieces:
            kind = piece.get("kind")
            data = piece.get("data")
            if kind == "demand" and data:
                # спрос: мерджим по годам (обновляем пришедшие, остальные оставляем)
                cur_years = base["demand"].get("years", {})
                new_years = data.get("years", {})
                cur_years.update({str(k): v for k, v in new_years.items()})
                base["demand"]["years"] = cur_years
                applied.append(f"demand ({len(new_years)} лет)")
            elif kind == "channels" and data:
                # мердж по id: обновляем совпадающие, добавляем новые, прочие храним
                by_id = {c["id"]: c for c in base["channels"]}
                for ch in data:
                    by_id[ch["id"]] = ch
                base["channels"] = list(by_id.values())
                applied.append(f"channels ({len(data)} обновлено)")
            elif kind == "storage" and data:
                base["storage"] = data
                applied.append("storage")
            elif kind == "investments" and data:
                # мердж по id
                by_id = {i["id"]: i for i in base["investments"]}
                for inv in data:
                    by_id[inv["id"]] = inv
                base["investments"] = list(by_id.values())
                applied.append(f"investments ({len(data)} обновлено)")
            # constraints не применяем автоматически (защита проверок)

        # пересобираем CaseData из обновлённого dict
        try:
            new_case = _rebuild_case(base)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Импорт не собрался в модель: {e}")

        state["case"] = new_case
        return {"applied": applied, "channels": [c.id for c in new_case.channels]}

    @app.post("/api/import/reset")
    def import_reset():
        """Вернуть исходные данные кейса (из data/case.yaml)."""
        state["case"] = load_case(DATA)
        return {"reset": True}

    # раздача собранного фронта (один процесс).
    # если фронт ещё не собран - пропускаем, API работает сам по себе.
    frontend_dist = ROOT / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="static")

    return app


app = create_app()
