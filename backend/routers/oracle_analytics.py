from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from backend.config import settings
from backend.services.postgres_service import get_simulations_by_ids, list_simulations_filtered

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics/oracle", tags=["oracle-analytics"])


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _risk_from_run(row: dict) -> float:
    raw = row.get("risk_of_backlash")
    try:
        return max(0.0, min(1.0, float(raw if raw is not None else 0.0)))
    except Exception:
        return 0.0


def _confidence_from_run(row: dict) -> float:
    raw = row.get("confidence")
    try:
        return max(0.0, min(1.0, float(raw if raw is not None else 0.0)))
    except Exception:
        return 0.0


def _tier_for_risk(risk: float) -> str:
    if risk >= 0.75:
        return "CRITICAL"
    if risk >= 0.50:
        return "ELEVATED"
    if risk >= 0.25:
        return "WATCH"
    return "NOMINAL"


def _result_to_score(row: dict) -> float:
    sentiment = row.get("predicted_sentiment") or {}
    pos = float(sentiment.get("positive", 0) or 0)
    neg = float(sentiment.get("negative", 0) or 0)
    return max(0.0, min(1.0, (pos + (1.0 - neg)) / 2.0))


def _chart_payload(rows: list[dict]) -> dict:
    ordered = sorted(rows, key=lambda x: x.get("created_at") or "")
    labels: list[str] = []
    risk_series: list[float] = []
    confidence_series: list[float] = []
    virality_series: list[float] = []
    tier_counter = Counter()
    sector_agg: dict[str, list[float]] = defaultdict(list)
    driver_counter = Counter()
    funnel = {"started": 0, "completed": 0, "actionable": 0, "confirmed": 0}

    for row in ordered:
        created = _parse_iso(row.get("created_at"))
        labels.append(created.strftime("%m-%d %H:%M") if created else "unknown")
        risk = _risk_from_run(row)
        conf = _confidence_from_run(row)
        virality = float(row.get("predicted_virality") or 0.0)
        risk_series.append(round(risk * 100, 2))
        confidence_series.append(round(conf * 100, 2))
        virality_series.append(round(max(0.0, min(1.0, virality)) * 100, 2))
        tier_counter[_tier_for_risk(risk)] += 1
        sector_agg[(row.get("sector") or "general").lower()].append(risk)
        funnel["started"] += 1
        if row.get("status") == "complete":
            funnel["completed"] += 1
        if risk >= 0.5:
            funnel["actionable"] += 1
        if risk >= 0.75 and conf >= 0.6:
            funnel["confirmed"] += 1
        for flag in (row.get("flags") or []):
            if isinstance(flag, str):
                driver_counter[flag] += 1

    moving: list[float] = []
    for idx in range(len(risk_series)):
        window = risk_series[max(0, idx - 4): idx + 1]
        moving.append(round(sum(window) / len(window), 2))

    sector_items = sorted(
        [{"sector": k, "avg_risk": round((sum(v) / len(v)) * 100, 2), "runs": len(v)} for k, v in sector_agg.items()],
        key=lambda x: x["avg_risk"],
        reverse=True,
    )
    compare_points = [
        {
            "x": round(_confidence_from_run(r) * 100, 2),
            "y": round(_risk_from_run(r) * 100, 2),
            "id": r.get("simulation_id"),
            "zone": r.get("zone"),
        }
        for r in ordered
    ]
    lead_time = []
    for r in ordered:
        created = _parse_iso(r.get("created_at"))
        completed = _parse_iso(r.get("completed_at"))
        if created and completed:
            lead_time.append(
                {
                    "label": created.strftime("%m-%d %H:%M"),
                    "minutes": max(0.0, round((completed - created).total_seconds() / 60.0, 2)),
                }
            )

    return {
        "timeline": {
            "labels": labels,
            "risk": risk_series,
            "risk_ma5": moving,
            "confidence": confidence_series,
            "virality": virality_series,
        },
        "tier_distribution": {
            "labels": ["NOMINAL", "WATCH", "ELEVATED", "CRITICAL"],
            "values": [
                tier_counter.get("NOMINAL", 0),
                tier_counter.get("WATCH", 0),
                tier_counter.get("ELEVATED", 0),
                tier_counter.get("CRITICAL", 0),
            ],
        },
        "confidence_vs_risk": compare_points,
        "sector_impact": sector_items,
        "driver_contribution": [{"driver": k, "count": v} for k, v in driver_counter.most_common(8)],
        "run_funnel": funnel,
        "lead_time": lead_time,
    }


def _build_final_outlook(rows: list[dict]) -> dict:
    if not rows:
        return {
            "final_outlook": {"tier": "NOMINAL", "probability": 0.0, "horizon_hours": 6},
            "key_drivers": ["Insufficient run history"],
            "recommended_actions": ["Run at least 5 Oracle simulations for this window."],
            "watch_signals": ["New high-risk runs", "Confidence trend drop"],
            "confidence_note": "Low confidence due to sparse data.",
        }

    recent = sorted(rows, key=lambda x: x.get("created_at") or "", reverse=True)[:20]
    avg_risk = sum(_risk_from_run(r) for r in recent) / max(1, len(recent))
    avg_conf = sum(_confidence_from_run(r) for r in recent) / max(1, len(recent))
    top_zones = Counter((r.get("zone") or "unknown") for r in recent).most_common(2)
    top_sectors = Counter((r.get("sector") or "general") for r in recent).most_common(2)
    tier = _tier_for_risk(avg_risk)
    playbook = {
        "decision_tier": tier,
        "trigger_thresholds": [
            "Escalate when CRITICAL appears in 2 consecutive runs.",
            "Escalate when ELEVATED with confidence >= 65%.",
            "De-escalate when 3 consecutive NOMINAL runs occur.",
        ],
        "invalidation_signals": [
            "Confidence drops below 40%",
            "Lead-time latency doubles vs baseline",
            "Opposing sentiment overtakes negative trend",
        ],
    }
    return {
        "final_outlook": {
            "tier": tier,
            "probability": round(avg_risk, 3),
            "horizon_hours": 6,
        },
        "key_drivers": [
            f"Recent average Oracle risk is {round(avg_risk * 100, 1)}%",
            f"Most active zones: {', '.join([z for z, _ in top_zones])}",
            f"Dominant sectors: {', '.join([s for s, _ in top_sectors])}",
        ],
        "recommended_actions": [
            "Escalate monitoring for top-risk zones in the next 6 hours.",
            "Cross-check elevated runs with live IRIS signals before public alerts.",
            "Trigger mitigation workflow when two consecutive CRITICAL forecasts appear.",
        ],
        "watch_signals": [
            "Confidence dropping below 45%",
            "Virality rising above 70%",
            "Run completion latency trending upward",
        ],
        "confidence_note": f"Model confidence is {round(avg_conf * 100, 1)}% based on recent completed runs.",
        "playbook": playbook,
    }


async def _build_rule_answer(question: str, rows: list[dict]) -> dict:
    q = (question or "").lower()
    if not rows:
        return {
            "answer": "No Oracle runs found for the selected filter window.",
            "confidence": 0.3,
            "evidence": [],
        }
    sorted_rows = sorted(rows, key=lambda x: x.get("created_at") or "", reverse=True)
    high = [r for r in sorted_rows if _risk_from_run(r) >= 0.5]
    top = max(sorted_rows, key=_risk_from_run)
    if "top" in q or "highest" in q:
        answer = (
            f"Highest-risk run is {top.get('simulation_id')} in {top.get('zone')} "
            f"with {_tier_for_risk(_risk_from_run(top))} risk ({round(_risk_from_run(top) * 100, 1)}%)."
        )
    elif "trend" in q or "increase" in q:
        latest = _risk_from_run(sorted_rows[0])
        earliest = _risk_from_run(sorted_rows[-1])
        direction = "up" if latest > earliest else "down"
        answer = f"Risk trend is {direction}: {round(earliest * 100, 1)}% -> {round(latest * 100, 1)}%."
    else:
        answer = (
            f"{len(high)} of {len(sorted_rows)} recent runs are actionable (>= ELEVATED). "
            f"Current top zone is {top.get('zone')}."
        )
    evidence = [
        {
            "simulation_id": r.get("simulation_id"),
            "zone": r.get("zone"),
            "risk_pct": round(_risk_from_run(r) * 100, 1),
            "confidence_pct": round(_confidence_from_run(r) * 100, 1),
            "created_at": r.get("created_at"),
        }
        for r in sorted_rows[:5]
    ]
    return {"answer": answer, "confidence": 0.76, "evidence": evidence}


async def _watsonx_augment(question: str, evidence: list[dict], draft_answer: str) -> str | None:
    if not settings.watsonx_api_key or not settings.watsonx_project_id:
        return None
    try:
        from ibm_watson_machine_learning.foundation_models import Model
    except Exception:
        return None
    try:
        model = Model(
            model_id=settings.watsonx_model_id,
            credentials={"apikey": settings.watsonx_api_key, "url": settings.watsonx_url},
            project_id=settings.watsonx_project_id,
            params={"max_new_tokens": 180, "temperature": 0.2},
        )
        payload = {
            "question": question,
            "draft_answer": draft_answer,
            "evidence": evidence[:5],
            "instruction": "Refine answer with concise 2-3 sentence executive summary. Do not invent facts.",
        }
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: model.generate_text(json.dumps(payload)))
        return (result or "").strip()[:800] or None
    except Exception as exc:
        logger.warning("Oracle analytics WatsonX augmentation failed: %s", exc)
        return None


@router.get("/history")
async def get_oracle_history(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    zone: str | None = None,
    sector: str | None = None,
    status: str | None = None,
    time_from: str | None = None,
    time_to: str | None = None,
):
    data = await list_simulations_filtered(
        limit=limit,
        offset=offset,
        zone=zone,
        sector=sector,
        status=status,
        time_from=_parse_iso(time_from),
        time_to=_parse_iso(time_to),
    )
    return data


@router.get("/charts")
async def get_oracle_charts(
    limit: int = Query(default=120, ge=10, le=1000),
    zone: str | None = None,
    sector: str | None = None,
    status: str | None = "complete",
    days: int = Query(default=14, ge=1, le=365),
):
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=max(1, days))
    data = await list_simulations_filtered(
        limit=limit,
        offset=0,
        zone=zone,
        sector=sector,
        status=status,
        time_from=start,
        time_to=now,
    )
    rows = data.get("items", [])
    return {"charts": _chart_payload(rows), "meta": {"count": len(rows), "days": days}}


@router.post("/compare")
async def compare_oracle_runs(payload: dict):
    ids = payload.get("simulation_ids") or []
    ids = [str(v) for v in ids if v][:3]
    rows = await get_simulations_by_ids(ids)
    return {"items": rows, "charts": _chart_payload(rows)}


@router.post("/chat")
async def oracle_chat(payload: dict):
    question = str(payload.get("question") or "").strip()
    if not question:
        return {"ok": False, "error": "question is required"}

    rows_data = await list_simulations_filtered(
        limit=min(200, int(payload.get("limit", 120) or 120)),
        offset=0,
        zone=payload.get("zone"),
        sector=payload.get("sector"),
        status=payload.get("status") or "complete",
        time_from=_parse_iso(payload.get("time_from")),
        time_to=_parse_iso(payload.get("time_to")),
    )
    rows = rows_data.get("items", [])
    rule = await _build_rule_answer(question, rows)
    refined = await _watsonx_augment(question, rule["evidence"], rule["answer"])
    used_watsonx = bool(refined)
    return {
        "ok": True,
        "answer": refined or rule["answer"],
        "evidence": rule["evidence"],
        "confidence": round((rule["confidence"] + (0.06 if used_watsonx else 0.0)), 2),
        "mode_used": "watsonx" if used_watsonx else "rule_based",
        "fallback_used": not used_watsonx,
    }


@router.get("/final-insight")
async def get_final_insight(
    zone: str | None = None,
    sector: str | None = None,
    days: int = Query(default=7, ge=1, le=90),
):
    now = datetime.now(timezone.utc)
    rows_data = await list_simulations_filtered(
        limit=200,
        offset=0,
        zone=zone,
        sector=sector,
        status="complete",
        time_from=now - timedelta(days=days),
        time_to=now,
    )
    rows = rows_data.get("items", [])
    insight = _build_final_outlook(rows)
    return {"ok": True, **insight, "meta": {"sample_size": len(rows), "window_days": days}}
