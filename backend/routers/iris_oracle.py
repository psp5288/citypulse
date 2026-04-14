from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.core.models import OracleForecastRequest
from backend.services.iris_service import get_iris_state, get_iris_trend
from backend.services.oracle_eval_service import compute_calibration_report
from backend.services.oracle_forecast_service import run_oracle_forecast
from backend.services.postgres_service import get_oracle_forecast

router = APIRouter()


@router.get("/iris/state")
async def iris_state(
    location: str = Query(..., min_length=2),
    topic: str = Query(..., min_length=2),
):
    return await get_iris_state(location=location, topic=topic, lookback_hours=24)


@router.get("/iris/trend")
async def iris_trend(
    location: str = Query(..., min_length=2),
    topic: str = Query(..., min_length=2),
    buckets: int = Query(default=12, ge=4, le=48),
):
    trend = await get_iris_trend(location=location, topic=topic, buckets=buckets, lookback_hours=24)
    return {
        "location": location,
        "topic": topic,
        "buckets": buckets,
        "trend": trend,
    }


@router.post("/oracle/forecast")
async def create_oracle_forecast(request: OracleForecastRequest):
    return await run_oracle_forecast(request)


@router.get("/oracle/forecast/{forecast_id}")
async def read_oracle_forecast(forecast_id: str):
    found = await get_oracle_forecast(forecast_id)
    if not found:
        raise HTTPException(status_code=404, detail="forecast_not_found")
    return found


@router.get("/oracle/calibration")
async def oracle_calibration(
    location: str = Query(..., min_length=2),
    topic: str = Query(..., min_length=2),
):
    return await compute_calibration_report(location=location, topic=topic)
