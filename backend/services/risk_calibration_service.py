from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def apply_affine_calibration(raw_score: float, alpha: float, beta: float) -> float:
    return max(0.0, min(1.0, alpha * raw_score + beta))


async def get_calibration_params(district_id: str, min_samples: int = 40) -> dict:
    """
    Lightweight calibration scaffold.
    Computes affine transform from resolved outcomes:
      calibrated = alpha * raw + beta
    """
    from backend.database import get_pool

    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT risk_score, significant_event
               FROM risk_predictions
               WHERE district_id = $1
                 AND outcome_recorded_at IS NOT NULL
               ORDER BY predicted_at DESC
               LIMIT 500""",
            district_id,
        )
    if len(rows) < min_samples:
        return {"enabled": False, "alpha": 1.0, "beta": 0.0, "n": len(rows), "method": "identity_insufficient_data"}

    scores = [float(r["risk_score"]) for r in rows]
    labels = [1.0 if bool(r["significant_event"]) else 0.0 for r in rows]
    mean_s = sum(scores) / len(scores)
    mean_y = sum(labels) / len(labels)
    var_s = sum((s - mean_s) ** 2 for s in scores) / max(1, len(scores))
    cov_sy = sum((scores[i] - mean_s) * (labels[i] - mean_y) for i in range(len(scores))) / max(1, len(scores))
    if var_s <= 1e-9:
        return {"enabled": False, "alpha": 1.0, "beta": 0.0, "n": len(rows), "method": "identity_low_variance"}

    alpha = max(0.1, min(2.0, cov_sy / var_s))
    beta = max(-0.5, min(0.5, mean_y - alpha * mean_s))
    return {"enabled": True, "alpha": round(alpha, 6), "beta": round(beta, 6), "n": len(rows), "method": "affine"}
