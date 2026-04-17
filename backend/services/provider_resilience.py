from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from backend.config import settings


@dataclass
class ProviderState:
    name: str
    failure_threshold: int = field(default_factory=lambda: max(1, settings.provider_default_failure_threshold))
    cooldown_seconds: int = field(default_factory=lambda: max(5, settings.provider_default_cooldown_seconds))
    consecutive_failures: int = 0
    open_until_monotonic: float = 0.0
    metrics: dict = field(default_factory=lambda: {
        "requests": 0,
        "success": 0,
        "failures": 0,
        "retries": 0,
        "cache_hits": 0,
        "stale_served": 0,
        "circuit_opens": 0,
    })
    latencies_ms: deque = field(default_factory=lambda: deque(maxlen=300))
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def circuit_open(self) -> bool:
        return time.monotonic() < self.open_until_monotonic


_providers: dict[str, ProviderState] = {}


def get_provider(name: str) -> ProviderState:
    if name not in _providers:
        _providers[name] = ProviderState(name=name)
    return _providers[name]


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * p))
    idx = max(0, min(idx, len(ordered) - 1))
    return float(ordered[idx])


async def with_resilience(
    provider_name: str,
    action: Callable[[], Awaitable[dict | list | None]],
    *,
    retries: int | None = None,
    backoff_base_ms: int | None = None,
) -> dict | list | None:
    provider = get_provider(provider_name)
    max_retries = retries if retries is not None else max(1, settings.provider_default_retry_attempts)
    base_ms = backoff_base_ms if backoff_base_ms is not None else max(100, settings.provider_default_backoff_base_ms)

    if provider.circuit_open():
        async with provider.lock:
            provider.metrics["failures"] += 1
        return None

    for attempt in range(1, max_retries + 1):
        started = time.monotonic()
        async with provider.lock:
            provider.metrics["requests"] += 1
        try:
            out = await action()
            elapsed = (time.monotonic() - started) * 1000
            async with provider.lock:
                provider.metrics["success"] += 1
                provider.consecutive_failures = 0
                provider.latencies_ms.append(elapsed)
            return out
        except Exception:
            elapsed = (time.monotonic() - started) * 1000
            async with provider.lock:
                provider.metrics["failures"] += 1
                provider.consecutive_failures += 1
                provider.latencies_ms.append(elapsed)
                if provider.consecutive_failures >= provider.failure_threshold:
                    if time.monotonic() >= provider.open_until_monotonic:
                        provider.open_until_monotonic = time.monotonic() + provider.cooldown_seconds
                        provider.metrics["circuit_opens"] += 1
            if attempt < max_retries:
                async with provider.lock:
                    provider.metrics["retries"] += 1
                await asyncio.sleep((base_ms * (2 ** (attempt - 1))) / 1000.0)
                continue
            return None
    return None


async def mark_cache_hit(provider_name: str) -> None:
    p = get_provider(provider_name)
    async with p.lock:
        p.metrics["cache_hits"] += 1


async def mark_stale_served(provider_name: str) -> None:
    p = get_provider(provider_name)
    async with p.lock:
        p.metrics["stale_served"] += 1


async def get_provider_snapshot(provider_name: str) -> dict:
    p = get_provider(provider_name)
    async with p.lock:
        metrics = dict(p.metrics)
        lat = list(p.latencies_ms)
        remaining = max(0.0, p.open_until_monotonic - time.monotonic())
        circuit_open = p.circuit_open()
        failures = p.consecutive_failures
    req = metrics.get("requests", 0) or 0
    fail = metrics.get("failures", 0) or 0
    return {
        "provider": provider_name,
        "circuit": {
            "open": circuit_open,
            "consecutive_failures": failures,
            "open_for_seconds": round(remaining, 2),
            "failure_threshold": p.failure_threshold,
            "cooldown_seconds": p.cooldown_seconds,
        },
        "metrics": {
            **metrics,
            "error_rate": round(fail / req, 4) if req else 0.0,
            "p95_latency_ms": round(_percentile(lat, 0.95), 2),
            "latency_samples": len(lat),
        },
    }


async def get_all_provider_snapshots() -> dict:
    out = {}
    for name in sorted(_providers.keys()):
        out[name] = await get_provider_snapshot(name)
    return out
