"""FastAPI-приложение «Маршрутизатор 3.0» (Этап 6)."""
from __future__ import annotations

import io
import os
import zipfile
from dataclasses import replace

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from exporter.exporter import export_route
from exporter.geojson import build_geojson
from geocoder.offline import OfflineGeocoder
from geocoder.yandex import YandexGeocoder
from optimizer.models import HOME_ID, Point
from optimizer.pipeline import build_routes
from router import (
    ChainRoadDistance,
    GraphHopperRoadDistance,
    OfflineRoadDistance,
    OpenRouteServiceRoadDistance,
    OsrmRoadDistance,
    YandexRoadDistance,
)
from parser import (
    FileError,
    MarshrutizatorError,
    OptimizationError,
    ValidationError,
    parse_planning,
    read_template_header,
    require_extension,
    validate_template_header,
)

from .jobstore import JobStore
from .schemas import OptimizeRequest

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # python-dotenv не обязателен
    pass

store = JobStore()
geocoder = YandexGeocoder() if os.environ.get("YANDEX_GEOCODER_API_KEY") else OfflineGeocoder()

_road_key = os.environ.get("YANDEX_ROUTING_API_KEY") or os.environ.get("YANDEX_GEOCODER_API_KEY")
_road_providers = []
if _road_key:
    _road_providers.append(YandexRoadDistance())
if os.environ.get("GRAPHOPPER_API_KEY"):
    _road_providers.append(GraphHopperRoadDistance())
if os.environ.get("OPENROUTESERVICE_API_KEY"):
    _road_providers.append(OpenRouteServiceRoadDistance())
if os.environ.get("OSRM_BASE_URL"):
    _road_providers.append(OsrmRoadDistance())
road_distance = ChainRoadDistance(_road_providers) if _road_providers else OfflineRoadDistance()

app = FastAPI(title="Маршрутизатор 3.0")


@app.exception_handler(MarshrutizatorError)
async def _domain_error_handler(request, exc: MarshrutizatorError):
    status = 422 if isinstance(exc, OptimizationError) else 400
    return JSONResponse(
        status_code=status,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )


def _human_address(p: Point) -> str:
    o = p.original
    parts = [
        o.get("Населенный пункт", ""),
        o.get("Тип улицы", ""),
        o.get("Название улицы", ""),
        o.get("Номер дома", ""),
        o.get("Номер строения", ""),
        o.get("Номер корпуса", ""),
    ]
    return ", ".join(str(x) for x in parts if str(x).strip())


def _geocode_points(points: list[Point]) -> list[Point]:
    out = []
    for p in points:
        if p.has_coords:
            out.append(p)
            continue
        ll = geocoder.geocode(_human_address(p))
        out.append(replace(p, latitude=ll[0], longitude=ll[1]) if ll else p)
    return out


def _geocode_home(address: str | None) -> tuple[float, float] | None:
    """Геокодирует домашний адрес; None, если адрес не задан или не найден."""
    if not address or not address.strip():
        return None
    ll = geocoder.geocode(address.strip())
    return (ll[0], ll[1]) if ll else None


def _build_road_matrix(points: list[Point], home: tuple[float, float] | None) -> dict | None:
    """Строит матрицу дорожных расстояний по id узлов (точки + дом).

    Возвращает {(id_a, id_b): км} или None (если провайдер недоступен/неполный).
    """
    nodes = [(p.id, (p.latitude, p.longitude)) for p in points if p.has_coords]
    if home is not None:
        nodes.append((HOME_ID, home))
    if len(nodes) < 2:
        return None

    matrix = road_distance.matrix([coords for _, coords in nodes])
    if matrix is None:
        return None

    out: dict[tuple[str, str], float] = {}
    for i, (id_a, _) in enumerate(nodes):
        for j, (id_b, _) in enumerate(nodes):
            out[(id_a, id_b)] = matrix[i][j]
    return out


@app.post("/api/upload/planning")
async def upload_planning(file: UploadFile = File(...)):
    require_extension(file.filename or "")
    content = await file.read()
    points = parse_planning(io.BytesIO(content))
    fid = store.add_file(content)
    return {"file_id": fid, "filename": file.filename, "row_count": len(points), "columns": list(points[0].original.keys()) if points else []}


@app.post("/api/upload/route-template")
async def upload_route_template(file: UploadFile = File(...)):
    require_extension(file.filename or "")
    content = await file.read()
    header = read_template_header(io.BytesIO(content))
    validate_template_header(header)
    fid = store.add_file(content)
    return {"file_id": fid, "filename": file.filename, "columns": header}


@app.post("/api/optimize", status_code=202)
def optimize(req: OptimizeRequest):
    job_id = store.create_job()

    planning = store.get_file(req.planning_file_id)
    template = store.get_file(req.route_template_file_id)
    if planning is None or template is None:
        raise FileError("Файл не найден. Загрузите файлы заново")

    store.update(job_id, status="PARSING")
    points = parse_planning(io.BytesIO(planning))

    store.update(job_id, status="GEOCODING")
    points = _geocode_points(points)
    home = _geocode_home(req.home_address)

    missing = [p.id for p in points if not p.has_coords]
    if missing:
        raise OptimizationError(
            "Не удалось геокодировать все точки — без координат невозможно построить маршрут по дорогам",
            {"points": missing[:20], "count": len(missing)},
        )

    road_matrix = _build_road_matrix(points, home)
    node_count = len(points) + (1 if home is not None else 0)
    if node_count >= 2 and road_matrix is None:
        raise OptimizationError(
            "Не удалось получить дорожную матрицу ни от одного провайдера "
            "(Яндекс/GraphHopper/OpenRouteService/OSRM)"
        )

    store.update(job_id, status="OPTIMIZING")
    results = build_routes(
        points,
        req.period_start,
        req.period_end,
        job_id=job_id,
        work_on_weekends=req.work_on_weekends,
        home=home,
        road_matrix=road_matrix,
    )

    store.update(job_id, status="EXPORTING")
    points_by_id = {p.id: p for p in points}
    files = [
        (f"{r.trade_rep_code or 'route'}.xlsx", export_route(io.BytesIO(template), r, points_by_id))
        for r in results
    ]
    geojson = build_geojson(results, points_by_id, home=home)

    store.update(job_id, status="COMPLETED", results=results, xlsx_files=files, geojson=geojson)
    return {"job_id": job_id}


@app.get("/api/result/{job_id}")
def result(job_id: str):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Результат не найден")
    payload = {"job_id": job_id, "status": job["status"]}
    if job.get("error"):
        payload["error"] = job["error"]
    if job.get("results"):
        payload["stats"] = [
            {
                "employee": r.trade_rep_code,
                "total_points": r.stats.total_points,
                "total_visits": r.stats.total_visits,
                "per_day_load": r.stats.per_day_load,
                "score": r.stats.score,
                "violations": r.stats.violations,
                "warnings": r.warnings,
                "total_km": round(r.stats.total_km, 1),
            }
            for r in job["results"]
        ]
    return payload


@app.get("/api/result/{job_id}/geojson")
def result_geojson(job_id: str):
    job = store.get(job_id)
    if job is None or job.get("geojson") is None:
        raise HTTPException(status_code=404, detail="GeoJSON не найден")
    return job["geojson"]


@app.get("/api/download/{job_id}")
def download(job_id: str):
    job = store.get(job_id)
    if job is None or job.get("xlsx_files") is None:
        raise HTTPException(status_code=404, detail="Файл не найден")
    files = job["xlsx_files"]
    if len(files) == 1:
        name, content = files[0]
        return Response(
            content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files:
            zf.writestr(name, content)
    return Response(
        buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="routes.zip"'},
    )


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")
