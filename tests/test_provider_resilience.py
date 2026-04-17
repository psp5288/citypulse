from __future__ import annotations

import asyncio

from backend.services.provider_resilience import get_provider_snapshot, with_resilience


def test_provider_resilience_counts_success():
    async def ok():
        return {"ok": True}

    out = asyncio.run(with_resilience("unit_provider", ok, retries=1))
    snap = asyncio.run(get_provider_snapshot("unit_provider"))
    assert out == {"ok": True}
    assert snap["metrics"]["requests"] >= 1
    assert snap["metrics"]["success"] >= 1
