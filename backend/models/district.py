from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class DistrictScore(BaseModel):
    id: str
    name: str
    crowd_density: float = Field(ge=0, le=1, default=0.5)
    sentiment_score: float = Field(ge=0, le=1, default=0.5)
    safety_risk: float = Field(ge=0, le=1, default=0.3)
    weather_impact: float = Field(ge=0, le=1, default=0.2)
    events_count: int = Field(ge=0, default=0)
    confidence: float = Field(ge=0, le=1, default=0.5)
    summary: str = "No data"
    flags: list[str] = []
    updated_at: Optional[datetime] = None


class DistrictSnapshot(DistrictScore):
    snapshot_id: Optional[int] = None
    source_data: dict = {}
