"""
CityPulse — In-memory run-state store (MiroFish-style state machine).

Tracks live runner metadata (stage, heartbeat, cancel flag) separately from
the persisted SimulationResult so that GET /simulate/{id} can return fresh
progress data without hitting the database on every poll.

State lifecycle:
  starting → running → completed
                     ↘ failed
                     ↘ cancelled   (via stop endpoint)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


# ── State store (single-worker asyncio — no lock needed) ─────────────────────
_STORE: dict[str, dict[str, Any]] = {}


def init_run(simulation_id: str, *, n_agents: int) -> None:
    """Create a fresh run record when a simulation is accepted."""
    _STORE[simulation_id] = {
        "runner_status": "starting",
        "stage": "initialising",
        "last_heartbeat": _now(),
        "progress_pct": 0.0,
        "processed": 0,
        "total": n_agents,
        "_cancel": False,
    }


def update_run(simulation_id: str, **kwargs: Any) -> None:
    """Merge kwargs into the run record and refresh the heartbeat timestamp."""
    entry = _STORE.get(simulation_id)
    if entry is None:
        return
    entry.update(kwargs)
    entry["last_heartbeat"] = _now()


def get_run(simulation_id: str) -> dict[str, Any] | None:
    return _STORE.get(simulation_id)


def is_cancelled(simulation_id: str) -> bool:
    return _STORE.get(simulation_id, {}).get("_cancel", False)


def cancel_run(simulation_id: str) -> bool:
    """
    Request cancellation.  Returns True if the run existed and was cancellable,
    False if it wasn't found or was already terminal.
    """
    entry = _STORE.get(simulation_id)
    if entry is None:
        return False
    if entry["runner_status"] in ("completed", "failed", "cancelled"):
        return False
    entry["_cancel"] = True
    entry["runner_status"] = "cancelling"
    entry["last_heartbeat"] = _now()
    return True


def clear_run(simulation_id: str) -> None:
    """Remove the run record (called after terminal state is persisted)."""
    _STORE.pop(simulation_id, None)


# ── Public snapshot (strips internal _cancel key) ────────────────────────────

def public_snapshot(simulation_id: str) -> dict[str, Any] | None:
    entry = _STORE.get(simulation_id)
    if entry is None:
        return None
    return {k: v for k, v in entry.items() if not k.startswith("_")}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
