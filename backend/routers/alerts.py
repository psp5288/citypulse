from fastapi import APIRouter, Query
from typing import Optional, Literal

from backend.services.postgres_service import get_alerts, resolve_alert

router = APIRouter()


@router.get("/alerts")
async def list_alerts(
    status: Optional[Literal["open", "watching", "closed", "all"]] = Query(default="all"),
    severity: Optional[Literal["critical", "warning", "info"]] = Query(default=None),
    limit: int = Query(default=50, le=200),
):
    return await get_alerts(status=status, severity=severity, limit=limit)


@router.post("/alerts/{alert_id}/resolve")
async def resolve(alert_id: str):
    await resolve_alert(alert_id)
    return {"status": "resolved"}
