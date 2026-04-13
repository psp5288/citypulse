from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Literal


class Event(BaseModel):
    id: Optional[int] = None
    type: str
    district_id: str
    message: str
    metadata: dict = {}
    created_at: Optional[datetime] = None


class Alert(BaseModel):
    id: Optional[int] = None
    severity: Literal["critical", "warning", "info"]
    title: str
    description: str = ""
    district_id: str
    status: str = "open"
    created_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
