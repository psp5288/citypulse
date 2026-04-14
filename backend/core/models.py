from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum


class Sector(str, Enum):
    banking = "banking"
    government = "government"
    news = "news"
    crisis = "crisis"
    general = "general"


class ExternalFactorType(str, Enum):
    counter_rumour = "counter_rumour"
    authority_denial = "authority_denial"
    viral_controversy = "viral_controversy"
    confirmation_leak = "confirmation_leak"


class ExternalFactor(BaseModel):
    type: ExternalFactorType
    content: str
    inject_at_minute: int = 0


class ZoneScore(BaseModel):
    zone_id: str
    zone_name: str
    city: str
    lat: float
    lng: float
    crowd_density: float        # 0.0–1.0
    sentiment_score: float      # 0.0–1.0 (1 = very positive)
    safety_risk: float          # 0.0–1.0 (1 = high risk)
    reactivity: float           # 0.0–1.0
    summary: str
    scored_at: datetime
    stale: bool = False         # True if WatsonX failed, serving cached value
    post_count: int = 0


class SimulationRequest(BaseModel):
    zone: str
    news_item: str
    sector: Sector = Sector.general
    n_agents: int = 1000
    external_factors: List[ExternalFactor] = []


class AgentResult(BaseModel):
    agent_id: int
    archetype: str
    sentiment: str              # positive / negative / neutral
    action: str                 # share / ignore / counter / amplify
    intensity: float            # 0.0–1.0
    reasoning: str


class SimulationResult(BaseModel):
    simulation_id: str
    zone: str
    news_item: str
    sector: str
    n_agents: int
    status: str                 # running / complete / failed
    predicted_sentiment: Optional[dict] = None   # {positive, negative, neutral}
    predicted_virality: Optional[float] = None
    peak_reaction_time: Optional[str] = None
    risk_of_backlash: Optional[float] = None
    confidence: Optional[float] = None
    vs_real_time: Optional[dict] = None
    progress_pct: Optional[float] = None
    processed_agents: Optional[int] = None
    total_agents: Optional[int] = None
    action_breakdown: Optional[dict] = None
    recent_actions: Optional[List[dict]] = None
    prior_context: Optional[dict] = None
    forecast_distribution: Optional[dict] = None
    # Cascade + advanced analytics
    cascade_rounds: Optional[int] = None          # how many influence rounds ran
    rumour_risk: Optional[float] = None           # 0-1: probability false narrative spreads
    coalition_dynamic: Optional[str] = None       # consensus | polarised | fragmented
    temporal_timeline: Optional[List[dict]] = None  # [{minute, pos, neg, neu, cumulative_reach}, ...]
    archetype_breakdown: Optional[dict] = None    # per-archetype sentiment/action summary
    created_at: datetime
    completed_at: Optional[datetime] = None


class Alert(BaseModel):
    alert_id: str
    zone_id: str
    zone_name: str
    alert_type: str             # high_risk / sentiment_crash / crowd_spike
    message: str
    severity: str               # low / medium / high / critical
    triggered_at: datetime
    value: float
    threshold: float


class IrisEvent(BaseModel):
    source: str
    location: str
    topic: str
    sentiment: float
    engagement: float
    confidence: float
    payload: dict = {}
    occurred_at: datetime


class IrisReactionVector(BaseModel):
    location: str
    topic: str
    sentiment_score: float
    attention_score: float
    stability_score: float
    trust_score: float
    novelty_score: float
    reaction_score: float
    confidence: float
    volume: int
    freshness_seconds: int
    as_of: datetime


class OracleForecastRequest(BaseModel):
    location: str
    topic: str
    scenario_text: str
    horizon_hours: int = 6
    n_agents: int = 1000
    include_historical_analogs: bool = True


class OracleForecastResult(BaseModel):
    forecast_id: str
    location: str
    topic: str
    scenario_text: str
    horizon_hours: int
    reaction_prior: IrisReactionVector
    probabilities: dict
    timeline: list[dict]
    rationale: list[str]
    confidence: float
    analogs: list[dict] = []
    created_at: datetime


class ErrorEnvelope(BaseModel):
    ok: bool = False
    error: str
    detail: Optional[str] = None
