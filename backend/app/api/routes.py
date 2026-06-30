"""HTTP routes. Preserves the JSON contract the Next.js frontend already expects."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from ..schemas import HealthResponse
from ..services.climate import CoordinateError, get_climate_intelligence
from ..services.summary import to_business_summary, to_consumer_summary

logger = logging.getLogger("api")
router = APIRouter()

# Boston defaults, matching the previous behavior.
_DEFAULT_LAT = 42.3601
_DEFAULT_LNG = -71.0589


def _error(status: int, message: str, detail: str | None = None) -> JSONResponse:
    body: dict[str, str] = {"error": message}
    if detail:
        body["detail"] = detail
    return JSONResponse(status_code=status, content=body)


@router.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="climate-risk-api")


@router.get("/api/climate-intelligence")
async def climate_intelligence(
    lat: float = Query(_DEFAULT_LAT),
    lng: float = Query(_DEFAULT_LNG),
) -> JSONResponse:
    logger.info("climate_intelligence.query", extra={"lat": lat, "lng": lng})
    try:
        data = await get_climate_intelligence(lat, lng)
    except CoordinateError as exc:
        return _error(400, str(exc))
    except Exception as exc:  # upstream/aggregation failure
        logger.error("climate_intelligence.error", extra={"lat": lat, "lng": lng, "err": str(exc)})
        return _error(502, "Failed to load climate intelligence.", str(exc))
    return JSONResponse(content=data)


@router.get("/api/summary/consumer")
async def summary_consumer(
    lat: float = Query(_DEFAULT_LAT),
    lng: float = Query(_DEFAULT_LNG),
) -> JSONResponse:
    logger.info("summary_consumer.query", extra={"lat": lat, "lng": lng})
    try:
        payload = await get_climate_intelligence(lat, lng)
        return JSONResponse(content=to_consumer_summary(payload))
    except CoordinateError as exc:
        return _error(400, str(exc))
    except Exception as exc:
        logger.error("summary_consumer.error", extra={"lat": lat, "lng": lng, "err": str(exc)})
        return _error(502, "Could not build consumer summary from climate intelligence data.", str(exc))


@router.get("/api/summary/business")
async def summary_business(
    lat: float = Query(_DEFAULT_LAT),
    lng: float = Query(_DEFAULT_LNG),
) -> JSONResponse:
    logger.info("summary_business.query", extra={"lat": lat, "lng": lng})
    try:
        payload = await get_climate_intelligence(lat, lng)
        return JSONResponse(content=to_business_summary(payload))
    except CoordinateError as exc:
        return _error(400, str(exc))
    except Exception as exc:
        logger.error("summary_business.error", extra={"lat": lat, "lng": lng, "err": str(exc)})
        return _error(502, "Could not build business summary from climate intelligence data.", str(exc))
