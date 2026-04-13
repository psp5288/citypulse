from fastapi import APIRouter, Query

from backend.core.logger import LOG_BUFFER

router = APIRouter()


@router.get("/logs")
async def get_logs(limit: int = Query(default=20, ge=1, le=100)):
    entries = LOG_BUFFER[-limit:]
    level_map = {"info": "ok", "debug": "info", "warning": "warn", "error": "warn", "critical": "warn"}
    return [
        [e["timestamp"], level_map.get(e["level"], "info"), e["message"]]
        for e in entries
    ]
