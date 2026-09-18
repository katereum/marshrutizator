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
    OsrmRouteGeometry,
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
# Локальный/self-hosted OSRM — первый приоритет: без ключа и внешних лимитов,
# не троттлит в отличие от Яндекс.Маршрутизации. Ключевые провайдеры — fallback.
if os.environ.get("OSRM_BASE_URL"):
    _road_providers.append(OsrmRoadDistance())
if _road_key:
    _road_providers.append(YandexRoadDistance())
if os.environ.get("GRAPHOPPER_API_KEY"):
    _road_providers.append(GraphHopperRoadDistance())
if os.environ.get("OPENROUTESERVICE_API_KEY"):
    _road_providers.append(OpenRouteServiceRoadDistance())
road_distance = ChainRoadDistance(_road_providers) if _road_providers else OfflineRoadDistance()
route_geometry = OsrmRouteGeometry()

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

    def s(key: str) -> str:
        v = o.get(key)
        return str(v).strip() if v is not None else ""

    street = " ".join(x for x in [s("Тип улицы"), s("Название улицы")] if x)
    house = " ".join(x for x in [s("Номер дома"), s("Номер строения"), s("Номер корпуса")] if x)
    return ", ".join(x for x in [s("Населенный пункт"), street, house] if x)


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

    Запросы идут блоками (ограничение провайдеров на число точек в одном
    запросе), размер блока — ROAD_MATRIX_CHUNK (по умолчанию 45).
    Возвращает {(id_a, id_b): км} или None, если провайдер недоступен/неполный.
    """
    nodes = [(p.id, (p.latitude, p.longitude)) for p in points if p.has_coords]
    if home is not None:
        nodes.append((HOME_ID, home))
    n = len(nodes)
    if n < 2:
        return None

    try:
        chunk = max(1, int(os.environ.get("ROAD_MATRIX_CHUNK", "45")))
    except ValueError:
        chunk = 45
    blocks = [nodes[i : i + chunk] for i in range(0, n, chunk)]

    out: dict[tuple[str, str], float] = {}
    for origin_block in blocks:
        for dest_block in blocks:
            matrix = road_distance.matrix(
                [coords for _, coords in origin_block],
                [coords for _, coords in dest_block],
            )
            if matrix is None or len(matrix) != len(origin_block):
                return None
            for a, (id_a, _) in enumerate(origin_block):
                if len(matrix[a]) != len(dest_block):
                    return None
                for b, (id_b, _) in enumerate(dest_block):
                    out[(id_a, id_b)] = matrix[a][b]
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


def _build_route_geometries(
    results,
    points_by_id: dict,
    home: tuple[float, float] | None,
) -> dict[tuple[str, str], list[list[float]]]:
    """Строит дорожные полилинии для каждого дня маршрута.

    Возвращает {(trade_rep_code, date.isoformat()): [[lon, lat], ...]}.
    Лучшая попытка: если провайдер геометрии недоступен, день просто не попадёт
    в словарь, и GeoJSON откатится на прямую линию.
    """
    geometries: dict[tuple[str, str], list[list[float]]] = {}
    for result in results:
        for day in result.days:
            visit_coords = []
            for vid in day.ordered_visits:
                point = points_by_id.get(vid.rsplit("#", 1)[0])
                if point is not None and point.has_coords:
                    visit_coords.append((point.latitude, point.longitude))

            coords = []
            if home is not None:
                coords.append(home)
            coords.extend(visit_coords)
            if home is not None:
                coords.append(home)
            if len(coords) < 2:
                continue

            line = route_geometry.route(coords)
            if line is not None:
                geometries[(result.trade_rep_code, day.date.isoformat())] = line
    return geometries


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

    missing = [p for p in points if not p.has_coords]
    if missing:
        raise OptimizationError(
            "Не удалось геокодировать все точки — без координат невозможно "
            "построить маршрут по дорогам. Проверьте адреса и лимит геокодера.",
            {
                "count": len(missing),
                "points": [{"id": p.id, "address": _human_address(p)} for p in missing[:20]],
                "geocoder": getattr(geocoder, "last_error", None),
            },
        )

    road_matrix = _build_road_matrix(points, home)
    node_count = len(points) + (1 if home is not None else 0)
    if node_count >= 2 and road_matrix is None:
        errors = [
            f"{type(p).__name__}: {p.last_error}"
            for p in getattr(road_distance, "providers", [])
            if getattr(p, "last_error", None)
        ]
        message = (
            "Не удалось получить дорожную матрицу ни от одного провайдера "
            "(OSRM/Яндекс/GraphHopper/OpenRouteService). "
            "Если используете локальный OSRM — запустите его командой "
            "`./scripts/setup_osrm.sh start`"
        )
        if errors:
            message += ": " + "; ".join(errors)
        raise OptimizationError(message, {"providers": errors})

    store.update(job_id, status="OPTIMIZING")
    results = build_routes(
        points,
        req.period_start,
        req.period_end,
        job_id=job_id,
        work_on_weekends=req.work_on_weekends,
        home=home,
        road_matrix=road_matrix,
        focus=req.focus,
    )

    store.update(job_id, status="EXPORTING")
    points_by_id = {p.id: p for p in points}
    files = [
        (f"{r.trade_rep_code or 'route'}.xlsx", export_route(io.BytesIO(template), r, points_by_id))
        for r in results
    ]
    geometries = _build_route_geometries(results, points_by_id, home)
    geojson = build_geojson(results, points_by_id, home=home, geometries=geometries)

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
